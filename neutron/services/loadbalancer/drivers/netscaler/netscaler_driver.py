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
# @author: Youcef Laribi, Citrix

from oslo.config import cfg

from neutron.api.v2 import attributes
from neutron.common import constants as q_const
from neutron.common import rpc as q_rpc
from neutron.openstack.common import importutils
from neutron.openstack.common import log as logging
from neutron.openstack.common import rpc
from neutron.openstack.common.rpc import proxy
from neutron.plugins.common import constants
from neutron.services.loadbalancer.drivers import abstract_driver
from neutron.services.loadbalancer.drivers.netscaler.ncc_client import NSClient

LOG = logging.getLogger(__name__)


NETSCALER_CC_OPTS = [
    cfg.StrOpt(
        'netscaler_ncc_uri',
        help=_('The URL to reach the NetScaler Control Center Server'),
    ),
    cfg.StrOpt(
        'netscaler_ncc_username',
        help=_('Username to login to the NetScaler Control Center Server'),
    ),
    cfg.StrOpt(
        'netscaler_ncc_password',
        help=_('Password to login to the NetScaler Control Center Server'),
    )
]

cfg.CONF.register_opts(NETSCALER_CC_OPTS, 'netscaler_driver')

VIPS_RESOURCE = 'vips'
VIP_RESOURCE = 'vip'
POOLS_RESOURCE = 'pools'
POOL_RESOURCE = 'pool'
POOLMEMBERS_RESOURCE = 'members'
POOLMEMBER_RESOURCE = 'member'
MONITORS_RESOURCE = 'healthmonitors'
MONITOR_RESOURCE = 'healthmonitor'
PROV_SEGMT_ID = 'provider:segmentation_id'
PROV_NET_TYPE = 'provider:network_type'


class NetScalerPluginDriver(abstract_driver.LoadBalancerAbstractDriver):
    """ NetScaler LBaaS Plugin driver class."""
    def __init__(self, plugin):
        self.plugin = plugin
        self.pool_to_port_id = {}
        self.ncc_uri = cfg.CONF.netscaler_driver.netscaler_ncc_uri
        self.ncc_username = cfg.CONF.netscaler_driver.netscaler_ncc_username
        self.ncc_password = cfg.CONF.netscaler_driver.netscaler_ncc_password
        self.client = NSClient(self.ncc_uri,
                             self.ncc_username,
                             self.ncc_password)

    def create_vip(self, context, vip):
        """Creates a vip on a NetScaler device."""
        network_info = self._get_vip_network_info(context, vip)
        self._prepare_vip_for_creation(vip)
        vip = dict(vip.items() + network_info.items())
        LOG.debug(_("NetScaler driver vip creation: %s") % repr(vip))
        self.client.create_resource(context.tenant_id, VIPS_RESOURCE,
                                    VIP_RESOURCE, vip)

    def update_vip(self, context, old_vip, vip):
        """Updates a vip on a NetScaler device."""
        self._prepare_vip_for_update(vip)
        LOG.debug(_("NetScaler driver vip %s update: %s") % (old_vip["id"],
                  repr(vip)))
        resource_path = "%s/%s" % (VIPS_RESOURCE, old_vip["id"])
        self.client.update_resource(context.tenant_id, resource_path,
                                    VIP_RESOURCE, vip)

    def delete_vip(self, context, vip):
        """Deletes a vip on a NetScaler device."""
        resource_path = "%s/%s" % (VIPS_RESOURCE, vip["id"])
        self.client.remove_resource(context.tenant_id, resource_path)
        LOG.debug(_("NetScaler driver vip removal: %s") % vip["id"])
        self.plugin._delete_db_vip(context, vip['id'])

    def create_pool(self, context, pool):
        """Creates a pool on a NetScaler device."""
        network_info = self._get_pool_network_info(context, pool)
        #allocate a snat port/ipaddress on the subnet if one doesn't exist
        self._create_snatport_for_subnet_if_not_exists(context,
                                                       pool['tenant_id'],
                                                       pool['subnet_id'],
                                                       network_info)
        self._prepare_pool_for_creation(pool)
        pool = dict(pool.items() + network_info.items())
        LOG.debug(_("NetScaler driver pool creation: %s") % repr(pool))
        self.client.create_resource(context.tenant_id, POOLS_RESOURCE, 
                                    POOL_RESOURCE, pool)

    def update_pool(self, context, old_pool, pool):
        """Updates a pool on a NetScaler device."""
        if pool['subnet_id'] != old_pool['subnet_id']:
            # if this is the first pool using the new subnet,
            # then add a snat port/ipaddress to it.
            self._create_snatport_for_subnet_if_not_exists(context,
                                                           pool['tenant_id'],
                                                           pool['subnet_id'],
                                                           network_info)
            #remove the old snat port/ipaddress from old subnet
            #if this pool was the last pool using it.
            self._remove_snatport_for_subnet_if_not_used(context,
                                                    old_pool['tenant_id'],
                                                    old_pool['subnet_id'])
        self._prepare_pool_for_update(pool)
        LOG.debug(_("NetScaler driver pool %s update: %s") % (old_pool["id"], 
                                                              repr(pool)))
        resource_path = "%s/%s" % (POOLS_RESOURCE, old_pool["id"])
        self.client.update_resource(context.tenant_id, resource_path, 
                                    POOL_RESOURCE, pool)

    def delete_pool(self, context, pool):
        """Deletes a pool on a NetScaler device."""
        resource_path = "%s/%s" % (POOLS_RESOURCE, pool['id'])
        self.client.remove_resource(context.tenant_id, resource_path)
        self.plugin._delete_db_pool(context, pool['id'])
        LOG.debug(_("NetScaler driver pool removal: %s") % pool["id"])
        self._remove_snatport_for_subnet_if_not_used(context,
                                                     pool['tenant_id'],
                                                     pool['subnet_id'])

    def create_member(self, context, member):
        """Creates a pool member on a NetScaler device."""
        self._prepare_member_for_creation(member)
        LOG.debug(_("NetScaler driver poolmember creation: %s") % repr(member))
        self.client.create_resource(context.tenant_id, POOLMEMBERS_RESOURCE,
                                    POOLMEMBER_RESOURCE, member)

    def update_member(self, context, old_member, member):
        """Updates a pool member on a NetScaler device."""
        self._prepare_member_for_update(member)
        LOG.debug(_("NetScaler driver poolmember %s update: %s") %
                  (old_member["id"], repr(member)))
        resource_path = "%s/%s" % (POOLMEMBERS_RESOURCE, old_member["id"])
        self.client.update_resource(context.tenant_id, resource_path,
                                    POOLMEMBER_RESOURCE, member)

    def delete_member(self, context, member):
        """Deletes a pool member on a NetScaler device."""
        resource_path = "%s/%s" % (POOLMEMBERS_RESOURCE, member['id'])
        self.client.remove_resource(context.tenant_id, resource_path)
        LOG.debug(_("NetScaler driver poolmember removal: %s") % member["id"])
        self.plugin._delete_db_member(context, member['id'])

    def create_pool_health_monitor(self, context, health_monitor, pool_id):
        """Creates a pool health monitor on a NetScaler device."""
        LOG.debug(_("NetScaler driver healthmonitor creation: %s") %
                  repr(health_monitor))
        self.client.create_resource(context.tenant_id, MONITORS_RESOURCE,
                                    MONITOR_RESOURCE,
                                    health_monitor)

    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool_id):
        """Updates a pool health monitor on a NetScaler device."""
        LOG.debug(_("NetScaler driver healthmonitor %s update: %s") %
                  (old_health_monitor["id"], repr(health_monitor)))
        resource_path = "%s/%s" % (MONITORS_RESOURCE, 
                                   old_health_monitor["id"])
        self.client.update_resource(context.tenant_id, resource_path,
                                     MONITOR_RESOURCE,
                                     health_monitor)

    def delete_pool_health_monitor(self, context, health_monitor, pool_id):
        """Deletes a pool health monitor on a NetScaler device."""
        resource_path = "%s/%s" % (MONITORS_RESOURCE, 
                                   health_monitor["id"])
        self.client.remove_resource(context.tenant_id, resource_path)
        LOG.debug(_("NetScaler driver healthmonitor removal: %s") %
                  health_monitor["id"])
        self.plugin._delete_db_pool_health_monitor(context,
                                                   health_monitor['id'],
                                                   pool_id)

    def stats(self, context, pool_id):
        """Retrieves pool statistics from a NetScaler device."""
        #TODO
        pass

    def _prepare_vip_for_creation(self, vip):
        del vip["status"]
        del vip["status_description"]
        del vip["port_id"]

    def _prepare_vip_for_update(self, vip):
        del vip["subnet_id"]
        del vip["protocol"]
        del vip["protocol_port"]
        del vip["address"]
        del vip["port_id"]
        del vip["status"]
        del vip["status_description"]

    def _prepare_pool_for_creation(self, pool):
        del pool["members"]
        del pool["health_monitors"]
        del pool["health_monitors_status"]
        del pool["status"]
        del pool["status_description"]
        del pool["provider"]

    def _prepare_pool_for_update(self, pool):
        del pool["provider"]
        del pool["status"]
        del pool["status_description"]
        del pool["members"]
        del pool["health_monitors"]
        del pool["health_monitors_status"]
        del pool["subnet_id"]
        del pool["vip_id"]
        del pool["protocol"]
        del pool["id"]
        del pool["tenant_id"]

    def _prepare_member_for_creation(self, member):
        del member["status"]
        del member["status_description"]

    def _prepare_member_for_update(self, member):
        del member["id"]
        del member["tenant_id"]
        del member["address"]
        del member["protocol_port"]
        del member["status"]
        del member["status_description"]

    def _prepare_healthmonitor_for_creation(self, health_monitor):
        del health_monitor["status"]
        del health_monitor["status_description"]

    def _prepare_healthmonitor_for_update(self, health_monitor):
        del health_monitor["id"]
        del health_monitor["tenant_id"]
        del health_monitor["status"]
        del health_monitor["status_description"]

    def _get_vip_network_info(self, context, vip):
        network_info = {}
        subnet_id = vip['subnet_id']
        subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
        network_id = subnet['network_id']
        network = self.plugin._core_plugin.get_network(context, network_id)
        network_info['port_id'] = vip['port_id']
        network_info['network_id'] = subnet['network_id']
        network_info['subnet_id'] = subnet_id
        if PROV_NET_TYPE in network:
            network_info['network_type'] = network[PROV_NET_TYPE]
        if PROV_SEGMT_ID in network:
            network_info['segmentation_id'] = network[PROV_SEGMT_ID]
        return network_info

    def _get_pool_network_info(self, context, pool):
        network_info = {}
        subnet_id = pool['subnet_id']
        subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
        network_id = subnet['network_id']
        network = self.plugin._core_plugin.get_network(context, network_id)
        network_info['network_id'] = network_id
        network_info['subnet_id'] = subnet_id
        if PROV_NET_TYPE in network:
            network_info['network_type'] = network[PROV_NET_TYPE]
        if PROV_SEGMT_ID in network:
            network_info['segmentation_id'] = network[PROV_SEGMT_ID]
        return network_info

    def _get_pools_on_subnet(self, context, tenant_id, subnet_id):
        filter_dict = {'subnet_id': [subnet_id], 'tenant_id': [tenant_id]}
        pools = self.plugin.get_pools(context, filters=filter_dict)
        return pools

    def _get_snatport_for_subnet(self, context, tenant_id, subnet_id):
        name = '_lb-snatport-' + subnet_id
        subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
        network_id = subnet['network_id']
        msg = _("Filtering ports based on network_id=%(network_id)s, "
                "tenant_id=%(tenant_id)s, name=%(name)s")
        LOG.debug(msg % {"network_id": network_id,
                       "tenant_id": tenant_id,
                       "name": name})
        filter_dict = {
                       'network_id': [network_id],
                       'tenant_id': [tenant_id],
                       'name': [name],
        }
        ports = self.plugin._core_plugin.get_ports(context,
                                                   filters=filter_dict)
        if ports:
            LOG.info(_("Found an existing SNAT port for subnet %s") %
                     subnet_id)
            return ports[0]
        LOG.info(_("Found no SNAT ports for subnet %s") % subnet_id)
        return None

    def _create_snatport_for_subnet(self, context, tenant_id, subnet_id,
                                    ip_address):
        subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
        fixed_ip = {'subnet_id': subnet['id']}
        if ip_address and ip_address != attributes.ATTR_NOT_SPECIFIED:
            fixed_ip['ip_address'] = ip_address
        port_data = {
            'tenant_id': tenant_id,
            'name': '_lb-snatport-' + subnet_id,
            'network_id': subnet['network_id'],
            'mac_address': attributes.ATTR_NOT_SPECIFIED,
            'admin_state_up': False,
            'device_id': '',
            'device_owner': '',
            'fixed_ips': [fixed_ip],
        }
        port = self.plugin._core_plugin.create_port(context,
                                                    {'port': port_data})
        LOG.info(_("Created SNAT port: %s") % repr(port))
        return port

    def _remove_snatport_for_subnet(self, context, tenant_id, subnet_id):
        port = self._get_snatport_for_subnet(context, tenant_id, subnet_id)
        if port:
            self.plugin._core_plugin.delete_port(context, port['id'])
            LOG.info(_("Removed SNAT port: %s") % repr(port))

    def _create_snatport_for_subnet_if_not_exists(self, context, tenant_id,
                                                  subnet_id, network_info):
        port = self._get_snatport_for_subnet(context, tenant_id, subnet_id)
        if not port:
            LOG.info(_("No SNAT port found for subnet %s. Creating one...") %
                       subnet_id)
            port = self._create_snatport_for_subnet(context, tenant_id,
                                                    subnet_id,
                                                    ip_address=None)
        network_info['port_id'] = port['id']
        network_info['snat_ip'] = port['fixed_ips'][0]['ip_address']
        LOG.info(_("SNAT port: %s") % repr(port))

    def _remove_snatport_for_subnet_if_not_used(self, context, tenant_id,
                                                subnet_id):
        pools = self._get_pools_on_subnet(context, tenant_id, subnet_id)
        if not pools:
            #No pools left on the old subnet.
            #We can remove the SNAT port/ipaddress
            self._remove_snatport_for_subnet(context, tenant_id, subnet_id)
            msg = _("Removing SNAT port for subnet %s as it is the "
                       "last pool using it...")
            LOG.info(msg % subnet_id)

