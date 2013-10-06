# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2013 New Dream Network, LLC (DreamHost)
# Copyright 2013 Citrix Systems, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Mark McClain, DreamHost
# @author: Youcef Laribi, Citrix

import weakref

from oslo.config import cfg

from neutron.agent.common import config
from neutron.agent import rpc as agent_rpc
from neutron.common import constants
from neutron import context
from neutron.openstack.common import importutils
from neutron.openstack.common import log as logging
from neutron.openstack.common import loopingcall
from neutron.openstack.common import periodic_task
from neutron.services.loadbalancer.drivers.netscaler import (
    agent_api,
    plugin_driver
)

LOG = logging.getLogger(__name__)
NS_PREFIX = 'qlbaas-'


OPTS = [
    cfg.StrOpt(
        'device_driver',
        default=('neutron.services.loadbalancer.drivers'
                 '.netscaler.netscaler_ncc_driver.AgentDriver'),
        help=_('The driver used to manage the NetScaler devices'),
    ),
    cfg.StrOpt(
        'agent_bind_host',
        default='0.0.0.0',
        help=_('The host IP address on which the lbaas agent listens'),
    ),
    cfg.StrOpt(
        'agent_bind_port',
        default='20371',
        help=_('The host port address on which the lbaas agent listens')
    )
]


class LogicalDeviceCache(object):
    """Manage a cache of known devices."""

    class Device(object):
        """Inner classes used to hold values for weakref lookups."""
        def __init__(self, port_id, pool_id):
            self.port_id = port_id
            self.pool_id = pool_id

        def __eq__(self, other):
            return self.__dict__ == other.__dict__

        def __hash__(self):
            return hash((self.port_id, self.pool_id))

    def __init__(self):
        self.devices = set()
        self.port_lookup = weakref.WeakValueDictionary()
        self.pool_lookup = weakref.WeakValueDictionary()

    def put(self, device):
        port_id = device['vip']['port_id']
        pool_id = device['pool']['id']
        d = self.Device(device['vip']['port_id'], device['pool']['id'])
        if d not in self.devices:
            self.devices.add(d)
            self.port_lookup[port_id] = d
            self.pool_lookup[pool_id] = d

    def remove(self, device):
        if not isinstance(device, self.Device):
            device = self.Device(
                device['vip']['port_id'], device['pool']['id']
            )
        if device in self.devices:
            self.devices.remove(device)

    def remove_by_pool_id(self, pool_id):
        d = self.pool_lookup.get(pool_id)
        if d:
            self.devices.remove(d)

    def get_by_pool_id(self, pool_id):
        return self.pool_lookup.get(pool_id)

    def get_by_port_id(self, port_id):
        return self.port_lookup.get(port_id)

    def get_pool_ids(self):
        return self.pool_lookup.keys()


class LbaasAgentManager(periodic_task.PeriodicTasks):

    # history
    #   1.0 Initial version
    #   1.1 Support agent_updated call
    RPC_API_VERSION = '1.1'

    def __init__(self, conf):
        self.conf = conf

        try:
            self.driver = importutils.import_object(
                conf.device_driver, self.conf)
        except ImportError:
            msg = _('Error importing loadbalancer device driver: %s')
            raise SystemExit(msg % conf.device_driver)

        self.agent_state = {
            'binary': 'neutron-loadbalancer-agent',
            'host': conf.host,
            'topic': plugin_driver.TOPIC_LOADBALANCER_AGENT,
            'configurations': {'device_driver': conf.device_driver},
            'agent_type': constants.AGENT_TYPE_LOADBALANCER,
            'start_flag': True}
        self.admin_state_up = True

        self.context = context.get_admin_context_without_session()
        self._setup_rpc()
        self.needs_resync = False
        self.cache = LogicalDeviceCache()

    def _setup_rpc(self):
        self.plugin_rpc = agent_api.LbaasAgentApi(
            plugin_driver.TOPIC_LOADBALANCER_DEVICE,
            self.context,
            self.conf.host
        )
        self.state_rpc = agent_rpc.PluginReportStateAPI(
            plugin_driver.TOPIC_LOADBALANCER_DEVICE)
        report_interval = self.conf.AGENT.report_interval
        if report_interval:
            heartbeat = loopingcall.FixedIntervalLoopingCall(
                self._report_state)
            heartbeat.start(interval=report_interval)

    def _report_state(self):
        try:
            device_count = len(self.cache.devices)
            self.agent_state['configurations']['devices'] = device_count
            self.state_rpc.report_state(self.context,
                                        self.agent_state)
            self.agent_state.pop('start_flag', None)
        except Exception:
            LOG.exception(_("Failed reporting state!"))


    @periodic_task.periodic_task(spacing=6)
    def collect_stats(self, context):
        for pool_id in self.cache.get_pool_ids():
            try:
                stats = self.driver.get_stats(pool_id)
                if stats:
                    self.plugin_rpc.update_pool_stats(pool_id, stats)
            except Exception:
                LOG.exception(_('Error upating stats'))
                self.needs_resync = True


    def create_vip(self, context, vip, netinfo):
        """Handle RPC cast from plugin to reload a pool."""
        LOG.info(_("Agent received create_vip"))
        self.driver.create_vip(vip, netinfo)

    def update_vip(self, context, old_vip, vip, old_netinfo, netinfo):
        LOG.info(_("Agent received update_vip"))
        self.driver.update_vip(old_vip, vip, old_netinfo, netinfo)

    def delete_vip(self, context, vip, netinfo):
        LOG.info(_("Agent received delete_vip"))
        self.driver.delete_vip(vip, netinfo)

    def create_pool(self, context, pool, netinfo):
        LOG.info(_("Agent received create_pool"))
        self.driver.create_pool(pool, netinfo)

    def update_pool(self, context, old_pool, pool, old_netinfo, netinfo):
        LOG.info(_('Agent received update_pool...'))
        self.driver.update_pool(old_pool, pool, old_netinfo, netinfo)

    def delete_pool(self, context, pool, netinfo):
        LOG.info(_('Agent received delete_pool...'))
        self.driver.delete_pool(pool, netinfo)

    def create_member(self, context, member, netinfo):
        LOG.info(_('Agent received create_member...'))
        self.driver.create_member(member, netinfo)

    def update_member(self, context, old_member, member, old_netinfo, netinfo):
        LOG.info(_('Agent received update_member...'))
        self.driver.update_member(old_member, member, old_netinfo, netinfo)

    def delete_member(self, context, member, netinfo):
        LOG.info(_('Agent received delete_member...'))
        self.driver.delete_member(member, netinfo)

    def create_pool_health_monitor(self, context, health_monitor, pool_id, netinfo):
        LOG.info(_('Agent received create_pool_health_monitor...'))
        self.driver.create_pool_health_monitor(health_monitor, pool_id, netinfo)

    def update_health_monitor(self, context, old_health_monitor, health_monitor, pool_id, netinfo):
        LOG.info(_('Agent received update_health_monitor...'))
        self.driver.update_health_monitor(old_health_monitor, health_monitor, pool_id, netinfo)

    def delete_pool_health_monitor(self, context, health_monitor, pool_id, netinfo):
        LOG.info(_('Agent received delete_pool_health_monitor...'))
        self.driver.delete_pool_health_monitor(health_monitor, pool_id, netinfo)

    def stats(self, context, pool_id, host):
        LOG.info(_('Agent received stats...'))


    @periodic_task.periodic_task(spacing=6)
    def poll_for_pending_tasks(self, context):
       tasks = self.driver.get_tasks()

       for task in tasks:
           try:
              self._process_task(task)
           except:
              LOG.exception(_("processing task %s failed with an exception" % task["id"]))


    def remove_orphans(self):
        try:
            self.driver.remove_orphans(self.cache.get_pool_ids())
        except NotImplementedError:
            pass  # Not all drivers will support this


    def destroy_pool(self, context, pool_id=None, host=None):
        """Handle RPC cast from plugin to destroy a pool if known to agent."""
        if self.cache.get_by_pool_id(pool_id):
            self.destroy_device(pool_id)

    def agent_updated(self, context, payload):
        """Handle the agent_updated notification event."""
        if payload['admin_state_up'] != self.admin_state_up:
            self.admin_state_up = payload['admin_state_up']
            if self.admin_state_up:
                self.needs_resync = True
            else:
                for pool_id in self.cache.get_pool_ids():
                    self.destroy_device(pool_id)
            LOG.info(_("agent_updated by server side %s!"), payload)
