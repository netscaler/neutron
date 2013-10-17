# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
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

import os
import shutil
import socket

import netaddr

from oslo.config import cfg
from neutron.agent.linux import ip_lib
from neutron.agent.linux import utils
from neutron.common import exceptions
from neutron.openstack.common import log as logging
from neutron.plugins.common import constants
from neutron.services.loadbalancer import constants as lb_const

from neutron.services.loadbalancer.drivers.netscaler.rest_client import RESTClient

LOG = logging.getLogger(__name__)
NS_PREFIX = 'qlbaas-'


OPTS = [
    cfg.StrOpt(
        'netscaler_ncc_uri',
        help=_('The URL to reach the NetScaler Control Center Server'),
    ),
    cfg.StrOpt(
        'netscaler_ncc_username',
        default=('admin'),
        help=_('The username to use to login to the NetScaler Control Center Server'),
    ),
    cfg.StrOpt(
        'netscaler_ncc_password',
        help=_('The password to use to login to the NetScaler Control Center Server'),
    )
]



class AgentDriver(object):
    def __init__(self, conf):
        self.conf = conf
        self.conf.register_opts(OPTS)
        self.pool_to_port_id = {}

        self.ncc_uri = self.conf.netscaler_ncc_uri
        self.ncc_username = self.conf.netscaler_ncc_username
        self.ncc_password = self.conf.netscaler_ncc_password

        LOG.debug(_("NCC configuration found: uri=%s username=%s" % (self.ncc_uri, self.ncc_username)))
        headers ={'X-Tenant-ID':'53763', 'X-OpenStack-LBaaS-Agent':'netscaler-openstack-lbaas-agent'}

        self.client = RESTClient(self.ncc_uri, self.ncc_username, self.ncc_password, headers=headers)

    def create_vip(self, vip, netinfo):
        LOG.debug(_("NetScaler Driver received the VIP creation request:vip=%s netinfo=%s" % 
                    (repr(vip), repr(netinfo))))
        del vip["status"]       
        del vip["port_id"]

        vip = dict(vip.items() + netinfo.items())

        LOG.debug(_("The vip object to send to NCC is: %s" % repr(vip)))

        self.client.create_resource("vips", "vip", vip)

    def update_vip(self, old_vip, vip, old_netinfo, netinfo):
        LOG.debug(_("NetScaler Driver received the VIP creation request:vip=%s netinfo=%s" % 
                    (repr(vip), repr(netinfo))))

        self.client.update_resource("vips/" + old_vip["id"], "vip", vip)


    def delete_vip(self, vip, netinfo):
        LOG.debug(_("NetScaler Driver received the VIP deletion request: vip=%s netinfo=%s" % 
                   (repr(vip), repr(netinfo))))

        self.client.remove_resource("vips/" + vip['id'])

    def create_pool(self, pool, netinfo):
        LOG.debug(_("NetScaler Driver received the pool creation request:pool=%s netinfo=%s" % 
                    (repr(pool), repr(netinfo))))

        del pool["members"]
        del pool["health_monitors"]
        del pool["health_monitors_status"] 
        del pool["status"]       
        del pool["provider"]

        pool = dict(pool.items() + netinfo.items())

        self.client.create_resource("pools", "pool", pool)

    def update_pool(self, old_pool, pool, old_netinfo, netinfo):
        LOG.debug(_("NetScaler Driver received the pool update request:pool=%s netinfo=%s" % 
                    (repr(pool), repr(netinfo))))
        self.client.update_resource("pools/" + old_pool["id"], "pool", pool)

    def delete_pool(self, pool, netinfo):
        LOG.debug(_("NetScaler Driver received the pool deletion request:pool=%s netinfo=%s" % 
                    (repr(pool), repr(netinfo))))
        self.client.remove_resource("pools/" + pool['id'])

    def create_member(self, member, netinfo):
        LOG.debug(_("NetScaler Driver received the member creation request:member=%s netinfo=%s" % 
                    (repr(member), repr(netinfo))))

        del member["status"]  
     
        self.client.create_resource("members" , "member", member)

    def update_member(self, old_member, member, old_netinfo, netinfo):
        LOG.debug(_("NetScaler Driver received the member update request:old_member=%s member=%s netinfo=%s" % 
                    (repr(old_member), repr(member), repr(netinfo))))
        self.client.update_resource("members/" + old_member["id"], "member", member)

    def delete_member(self, member, netinfo):
        LOG.debug(_("NetScaler Driver received a member deletion request:member=%s netinfo=%s" % 
                    (repr(member), repr(netinfo))))
        self.client.remove_resource("members/" + member['id'])

    def create_pool_health_monitor(self, health_monitor, pool_id, netinfo):
        LOG.debug(_("NetScaler Driver received the health monitor creation request:health_monitor=%s netinfo=%s" % 
                    (repr(health_monitor), repr(netinfo))))
        self.client.create_resource("healthmonitors", "healthmonitor", health_monitor)

    def update_health_monitor(self, old_health_monitor, health_monitor, pool_id, netinfo):
        LOG.debug(_("NetScaler Driver received the health monitor update request:old_h=%s mealth_monitor health_monitor=%s netinfo=%s" % 
                    (repr(old_health_monitor), repr(health_monitor), repr(netinfo))))
        self.client.update_resource("healthmonitors/" + old_health_monitor["id"], "health_monitor", health_monitor)

    def delete_pool_health_monitor(self, health_monitor, pool_id, netinfo):
        LOG.debug(_("NetScaler Driver received a health monitor deletion request: health_monitor=%s netinfo=%s" % 
                    (repr(health_monitor), repr(netinfo))))
        self.client.remove_resource("healthmonitors/" + health_monitor['id'])

    def get_stats(self, pool_id):
        LOG.debug(_("NetScaler Driver received a stats collection request for pool %s" % pool_id))
        return None


    def get_tasks(self):
        LOG.debug(_("NetScaler Driver received a request to check for pending tasks on ncc"))
        return []
