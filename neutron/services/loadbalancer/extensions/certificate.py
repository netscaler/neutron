# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 OpenStack Foundation.
# All Rights Reserved.
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
#    @author: Youcef Laribi, Citrix
#

from abc import ABCMeta
from abc import abstractmethod

from oslo.config import cfg

from neutron.api import extensions
from neutron.api.v2 import attributes as attr
from neutron.api.v2 import base
from neutron.common import exceptions as qexception
from neutron import manager
from neutron.openstack.common import uuidutils
from neutron.plugins.common import constants
from neutron.openstack.common import log as logging

LOG = logging.getLogger(__name__)

RESOURCE_NAME = "certificate"
COLLECTION_NAME = "%ss" % RESOURCE_NAME
EXTENSION_ALIAS = 'certificates'



# Attribute Map
RESOURCE_ATTRIBUTE_MAP = {
    'certificates': {
        'id': {'allow_post': False, 'allow_put': False,
               'validate': {'type:uuid': None},
               'is_visible': True,
               'primary_key': True},
        'name': {'allow_post': True, 'allow_put': True,
                 'is_visible': True, 'default': '',
                 'validate': {'type:name_not_default': None}},
        'description': {'allow_post': True, 'allow_put': True,
                        'is_visible': True, 'default': ''},
        'tenant_id': {'allow_post': True, 'allow_put': False,
                      'required_by_policy': True,
                      'is_visible': True}
    }
}



CERTIFICATE = 'certificate'
CERTIFICATES = "%ss" % CERTIFICATE

CERTIFICATE_ID = '%s_id' % CERTIFICATE

EXTENDED_ATTRIBUTES_2_0 = {
    'vips': {'certificate_id': {'allow_post': True,
                            'allow_put': True,
                            'is_visible': True,
                            'default': attr.ATTR_NOT_SPECIFIED}}}


class CertificateNotFound(qexception.NotFound):
    message = _("Certificate %(id)s does not exist")


class CertificateInUse(qexception.InUse):
    message = _("Certificate %(id)s in use.")


class Certificate(extensions.ExtensionDescriptor):

    @classmethod
    def get_name(cls):
        return _("Neutron Service Certificate Management")

    @classmethod
    def get_alias(cls):
        return EXTENSION_ALIAS

    @classmethod
    def get_description(cls):
        return _("API for creating, updating and retrieving "
                 "certificates for loadbalancers")

    @classmethod
    def get_namespace(cls):
        return "http://docs.openstack.org/ext/neutron/certificate/api/v1.0"

    @classmethod
    def get_updated(cls):
        return "2013-10-02T00:00:00-00:00"

    @classmethod
    def get_resources(cls):
        """Returns Ext Resources."""
        my_plurals = [(key, key[:-1]) for key in RESOURCE_ATTRIBUTE_MAP.keys()]
        attr.PLURALS.update(dict(my_plurals))
        exts = []
        service_plugins = manager.NeutronManager.get_service_plugins()

        if service_plugins and constants.LOADBALANCER in service_plugins:
            plugin = service_plugins[constants.LOADBALANCER]
            resource_name = RESOURCE_NAME
            collection_name = resource_name.replace('_', '-') + "s"
            params = RESOURCE_ATTRIBUTE_MAP.get(resource_name + "s", dict())
            controller = base.create_resource(collection_name,
                                              resource_name,
                                              plugin, params, allow_bulk=True,
                                              allow_pagination=True,
                                              allow_sorting=True)

            ex = extensions.ResourceExtension(collection_name,
                                              controller,
                                              attr_map=params)
            exts.append(ex)

        return exts

    def get_extended_resources(self, version):
        if version == "2.0":
            return dict(EXTENDED_ATTRIBUTES_2_0.items() +
                        RESOURCE_ATTRIBUTE_MAP.items())
        else:
            return {}


class CertificatePluginBase(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def create_certificate(self, context, certificate):
        pass

    @abstractmethod
    def update_certificate(self, context, id, certificate):
        pass

    @abstractmethod
    def delete_certificate(self, context, id):
        pass

    @abstractmethod
    def get_certificates(self, context, filters=None, fields=None,
                            sorts=None, limit=None, marker=None,
                            page_reverse=False):
        pass

    @abstractmethod
    def get_certificate(self, context, id, fields=None):
        pass

