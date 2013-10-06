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

import sys

from neutron.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class NetScalerAgentController(object):


    def __init__(self):
        LOG.debug(_("NetScaler Agent Plugin initialization complete"))


    def create_vip_info(self, context, vip_info):
        session = context.session
        with session.begin(subtransactions=True):
            pass

        return vip_info

    def update_vip_info(self, context, id, vip_info):

        session = context.session
        with session.begin(subtransactions=True):
            pass

        return vip_info

    def delete_vip_info(self, context, id):
        session = context.session
        with session.begin(subtransactions=True):
            pass

    def get_vip_info(self, context, id, fields=None):
        session = context.session
        with session.begin(subtransactions=True):
            pass

        return self._fields({}, fields)

    def get_vips_info(self, context, filters=None, fields=None,
                     sorts=None, limit=None, marker=None, page_reverse=False):
        session = context.session
        with session.begin(subtransactions=True):
            pass

        return []

    def create_pool_info(self, context, pool_info):
        session = context.session

        with session.begin(subtransactions=True):
            pass

        return pool_info

    def update_pool_info(self, context, id, pool_info):
        original_pool_info = self.get_poo_info(context, id)
        session = context.session


        with session.begin(subtransactions=True):
            pass

        return original_pool_info

    def delete_pool_info(self, context, id, l3_port_check=True):

        session = context.session
        with session.begin(subtransactions=True):
            pass


    def get_pool_info(self, context, id, fields=None):
        session = context.session
        with session.begin(subtransactions=True):
            pass

        return self._fields({}, fields)


    def get_pools_info(self, context, filters=None, fields=None,
                     sorts=None, limit=None, marker=None, page_reverse=False):
        session = context.session
        with session.begin(subtransactions=True):
            pass

        return []
