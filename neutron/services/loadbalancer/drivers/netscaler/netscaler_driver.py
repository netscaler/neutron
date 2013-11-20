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


from oslo.config import cfg

from neutron.api.v2 import attributes
from neutron.db.loadbalancer import loadbalancer_db
from neutron.openstack.common import log as logging
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
POOLSTATS_RESOURCE = 'statistics'
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
        msg = _("NetScaler driver vip creation: %(vip_obj)s")
        LOG.debug(msg, {"vip_obj": repr(vip)})
        self.client.create_resource(context.tenant_id, VIPS_RESOURCE,
                                    VIP_RESOURCE, vip)
        self._set_status(context, loadbalancer_db.Vip,
                         vip, vip["id"],
                         constants.ACTIVE)

    def update_vip(self, context, old_vip, vip):
        """Updates a vip on a NetScaler device."""
        update_vip = self._prepare_vip_for_update(vip)
        resource_path = "%s/%s" % (VIPS_RESOURCE, vip["id"])
        msg = _("NetScaler driver vip %(vip_id)s update: %(vip_obj)s")
        LOG.debug(msg, {"vip_id": vip["id"], "vip_obj": repr(vip)})
        self.client.update_resource(context.tenant_id, resource_path,
                                    VIP_RESOURCE, update_vip)
        self._set_status(context, loadbalancer_db.Vip,
                         old_vip, old_vip["id"],
                         constants.ACTIVE)

    def delete_vip(self, context, vip):
        """Deletes a vip on a NetScaler device."""
        resource_path = "%s/%s" % (VIPS_RESOURCE, vip["id"])
        msg = _("NetScaler driver vip removal: %(vip_id)s")
        LOG.debug(msg, {"vip_id": vip["id"]})
        self.client.remove_resource(context.tenant_id, resource_path)
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
        msg = _("NetScaler driver pool creation: %(pool_obj)s")
        LOG.debug(msg, {"pool_obj": repr(pool)})
        self.client.create_resource(context.tenant_id, POOLS_RESOURCE,
                                    POOL_RESOURCE, pool)
        self._set_status(context, loadbalancer_db.Pool,
                         pool, pool["id"],
                         constants.ACTIVE)

    def update_pool(self, context, old_pool, pool):
        """Updates a pool on a NetScaler device."""
        if pool['subnet_id'] != old_pool['subnet_id']:
            # if this is the first pool using the new subnet,
            # then add a snat port/ipaddress to it.
            network_info = self._get_pool_network_info(context, pool)
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
        resource_path = "%s/%s" % (POOLS_RESOURCE, old_pool["id"])
        msg = _("NetScaler driver pool %(pool_id)s update: %(pool_obj)s")
        LOG.debug(msg, {"pool_id": old_pool["id"], "pool_obj": repr(pool)})
        self.client.update_resource(context.tenant_id, resource_path,
                                    POOL_RESOURCE, pool)
        self._set_status(context, loadbalancer_db.Pool,
                         old_pool, old_pool["id"],
                         constants.ACTIVE)

    def delete_pool(self, context, pool):
        """Deletes a pool on a NetScaler device."""
        resource_path = "%s/%s" % (POOLS_RESOURCE, pool['id'])
        msg = _("NetScaler driver pool removal: %(pool_id)s")
        LOG.debug(msg, {"pool_id": pool["id"]})
        self.client.remove_resource(context.tenant_id, resource_path)
        self.plugin._delete_db_pool(context, pool['id'])
        self._remove_snatport_for_subnet_if_not_used(context,
                                                 pool['tenant_id'],
                                                 pool['subnet_id'])

    def create_member(self, context, member):
        """Creates a pool member on a NetScaler device."""
        self._prepare_member_for_creation(member)
        msg = _("NetScaler driver poolmember creation: %(member_obj)s")
        LOG.debug(msg, {"member_obj": repr(member)})
        self.client.create_resource(context.tenant_id, POOLMEMBERS_RESOURCE,
                                    POOLMEMBER_RESOURCE, member)
        self._set_status(context, loadbalancer_db.Member,
                         member, member["id"],
                         constants.ACTIVE)

    def update_member(self, context, old_member, member):
        """Updates a pool member on a NetScaler device."""
        self._prepare_member_for_update(member)
        resource_path = "%s/%s" % (POOLMEMBERS_RESOURCE, old_member["id"])
        msg = _("NetScaler driver poolmember %(member_id)s update:"
                " %(member_obj)s")
        LOG.debug(msg, {"member_id": old_member["id"],
                        "member_obj": repr(member)})
        self.client.update_resource(context.tenant_id, resource_path,
                                        POOLMEMBER_RESOURCE, member)
        self._set_status(context, loadbalancer_db.Member,
                         old_member, old_member["id"],
                         constants.ACTIVE)

    def delete_member(self, context, member):
        """Deletes a pool member on a NetScaler device."""
        resource_path = "%s/%s" % (POOLMEMBERS_RESOURCE, member['id'])
        msg = _("NetScaler driver poolmember removal: %(member_id)s")
        LOG.debug(msg, {"member_id": member["id"]})
        self.client.remove_resource(context.tenant_id, resource_path)
        self.plugin._delete_db_member(context, member['id'])

    def create_pool_health_monitor(self, context, health_monitor, pool_id):
        """Creates a pool health monitor on a NetScaler device."""
        self._prepare_healthmonitor_for_creation(health_monitor, pool_id)
        resource_path = "%s/%s/%s" % (POOLS_RESOURCE, pool_id,
                                      MONITORS_RESOURCE)
        msg = _("NetScaler driver healthmonitor creation for pool %(pool_id)s"
                ": %(monitor_obj)s")
        LOG.debug(msg, {"pool_id": pool_id,
                        "monitor_obj": repr(health_monitor)})
        self.client.create_resource(context.tenant_id, resource_path,
                                    MONITOR_RESOURCE,
                                    health_monitor)
        self._set_poolhealthmonitor_status(context, health_monitor,
                                           pool_id, constants.ACTIVE)

    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool_id):
        """Updates a pool health monitor on a NetScaler device."""
        self._prepare_healthmonitor_for_update(health_monitor)
        resource_path = "%s/%s" % (MONITORS_RESOURCE,
                                   old_health_monitor["id"])
        msg = _("NetScaler driver healthmonitor %(monitor_id)s update: "
                "%(monitor_obj)s")
        LOG.debug(msg, {"monitor_id": old_health_monitor["id"],
                        "monitor_obj": repr(health_monitor)})
        self.client.update_resource(context.tenant_id, resource_path,
                                    MONITOR_RESOURCE, health_monitor)
        self._set_poolhealthmonitor_status(context, old_health_monitor,
                                           pool_id, constants.ACTIVE)

    def delete_pool_health_monitor(self, context, health_monitor, pool_id):
        """Deletes a pool health monitor on a NetScaler device."""
        resource_path = "%s/%s/%s/%s" % (POOLS_RESOURCE, pool_id,
                                         MONITORS_RESOURCE,
                                         health_monitor["id"])
        msg = _("NetScaler driver healthmonitor %(monitor_id)s"
                "removal for pool %(pool_id)s")
        LOG.debug(msg, {"monitor_id": health_monitor["id"],
                        "pool_id": pool_id})
        self.client.remove_resource(context.tenant_id, resource_path)
        self.plugin._delete_db_pool_health_monitor(context,
                                                   health_monitor['id'],
                                                   pool_id)

    def stats(self, context, pool_id):
        """Retrieves pool statistics from the NetScaler device."""
        resource_path = "%s/%s" % (POOLSTATS_RESOURCE, pool_id)
        msg = _("NetScaler driver pool stats retrieval: %(pool_id)s")
        LOG.debug(msg, {"pool_id": pool_id})
        _, stats = self.client.retrieve_resource(context.tenant_id,
                                                      resource_path)
        return stats

    def _prepare_vip_for_creation(self, vip):
        del vip["status"]
        del vip["status_description"]
        del vip["port_id"]

    def _prepare_vip_for_update(self, vip):
        return {'name': vip['name'],
                'description': vip['description'],
                'pool_id': vip['pool_id'],
                'connection_limit': vip['connection_limit'],
                'admin_state_up': vip['admin_state_up']
               }

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

    def _prepare_healthmonitor_for_creation(self, health_monitor, pool_id):
        del health_monitor["pools"]

    def _prepare_healthmonitor_for_update(self, health_monitor):
        del health_monitor["id"]
        del health_monitor["tenant_id"]
        del health_monitor["type"]
        del health_monitor["pools"]

    def _get_network_info(self, context, entity):
        network_info = {}
        subnet_id = entity['subnet_id']
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

    def _get_vip_network_info(self, context, vip):
        network_info = self._get_network_info(context, vip)
        network_info['port_id'] = vip['port_id']
        return network_info

    def _get_pool_network_info(self, context, pool):
        return self._get_network_info(context, pool)

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
        LOG.debug(msg, {"network_id": network_id,
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
            msg = _("Found an existing SNAT port for subnet %(subnet_id)s")
            LOG.info(msg, {"subnet_id": subnet_id})
            return ports[0]
        msg = _("Found no SNAT ports for subnet %(subnet_id)s")
        LOG.info(msg, {"subnet_id": subnet_id})

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
        msg = _("Created SNAT port: %(port_obj)s")
        LOG.info(msg, {"port_obj": repr(port)})
        return port

    def _remove_snatport_for_subnet(self, context, tenant_id, subnet_id):
        port = self._get_snatport_for_subnet(context, tenant_id, subnet_id)
        if port:
            self.plugin._core_plugin.delete_port(context, port['id'])
            msg = _("Removed SNAT port: %(port_obj)s")
            LOG.info(msg, {"port_obj": repr(port)})

    def _create_snatport_for_subnet_if_not_exists(self, context, tenant_id,
                                                  subnet_id, network_info):
        port = self._get_snatport_for_subnet(context, tenant_id, subnet_id)
        if not port:
            msg = _("No SNAT port found for subnet %(subnet_id)s."
                    " Creating one...")
            LOG.info(msg, {"subnet_id": subnet_id})
            port = self._create_snatport_for_subnet(context, tenant_id,
                                                    subnet_id,
                                                    ip_address=None)
        network_info['port_id'] = port['id']
        network_info['snat_ip'] = port['fixed_ips'][0]['ip_address']
        msg = _("SNAT port: %(port_obj)s")
        LOG.info(msg, {"port_obj": repr(port)})

    def _remove_snatport_for_subnet_if_not_used(self, context, tenant_id,
                                                subnet_id):
        pools = self._get_pools_on_subnet(context, tenant_id, subnet_id)
        if not pools:
            #No pools left on the old subnet.
            #We can remove the SNAT port/ipaddress
            self._remove_snatport_for_subnet(context, tenant_id, subnet_id)
            msg = _("Removing SNAT port for subnet %(subnet_id)s "
                    "as it is the last pool using it...")
            LOG.info(msg, {"subnet_id": subnet_id})

    def _set_status(self, context, model, entity, entity_id, status):
        self.plugin.update_status(context, model, entity_id, status)

    def _set_poolhealthmonitor_status(self, context, monitor, pool_id, status):
        # Cannot use self.plugin.update_status() here since a
        # PoolHealthMonitorAssociation takes 2 ids (pool_id and monitor_id)
        # while update_status() assumes a resource is identified by one ID,
        # so, we are updating status of this resource by direct access to DB.
        with context.session.begin(subtransactions=True):
            qry = context.session.query(loadbalancer_db.PoolMonitorAssociation)
            qry = qry.filter_by(monitor_id=monitor['id'], pool_id=pool_id)
            db_monitor = qry.one()
            db_monitor.status = status
