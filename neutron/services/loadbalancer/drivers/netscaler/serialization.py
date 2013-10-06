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

from xml.dom import minidom
from webob.exc import HTTPBadRequest

from neutron.services.loadbalancer.drivers.netscaler.format_utils import get_payload_from_object, get_dictionary_from_payload


class Serializer(object):
    """Serializes and deserializes dictionaries to certain MIME types."""

    def __init__(self, default_xmlns=None, plurals=None):
        self.default_xmlns = default_xmlns
        self.plurals = plurals 

 
    def serialize(self, object_name, data, content_type, xmlelementstyle=False):
        """Serialize a dictionary into the specified content type."""
        return get_payload_from_object(object_name, data, content_type, self.plurals, self.default_xmlns, xmlelementstyle)


    def deserialize(self, payload, content_type):
        """Deserialize a string to a dictionary."""

        try:
            return get_dictionary_from_payload(payload, content_type, self.plurals)

        except Exception:
            raise HTTPBadRequest("Could not deserialize data")


