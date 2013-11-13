# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2013 Citrix Systems
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


import base64
import httplib
import json
import sys
import urlparse

from neutron.common import exceptions as q_exc
from neutron.openstack.common import log as logging

LOG = logging.getLogger(__name__)

CONTENT_TYPE_HEADER = 'Content-type'
ACCEPT_HEADER = 'Accept'
AUTH_HEADER = 'Authorization'
DRIVER_HEADER = 'X-OpenStack-LBaaS'
TENANT_HEADER = 'X-Tenant-ID'
JSON_CONTENT_TYPE = 'application/json'
DRIVER_HEADER_VALUE = 'netscaler-openstack-lbaas'

HTTP_CREATE_METHOD = 'POST'
HTTP_READ_METHOD = 'GET'
HTTP_UPDATE_METHOD = 'PUT'
HTTP_DELETE_METHOD = 'DELETE'

HTTP_SCHEME = 'http'
HTTPS_SCHEME = 'https'

HTTP_DEFAULT_PORT = 80
HTTPS_DEFAULT_PORT = 443

HTTP_AUTH_FAILURE_STATUSCODE = '401'


class NSClient:
    """Client to operate on REST resources of NetScaler Control Center. """
    def __init__(self, uri, username, password):
        if not uri:
            msg = _("No NetScaler Control Center URI specified. Cannot connect.")
            LOG.error(msg)
            raise Exception(msg)
        self._parse_uri(uri)
        self.auth = None
        if username != None and password != None:
            base64string = base64.encodestring("%s:%s" % (username, password))
            base64string = base64string[:-1]
            self.auth = 'Basic %s' % base64string

    def create_resource(self, tenant_id, resource_path, object_name, object_data):
        """Creates an HTTP REST resource of NetScaler Control Center."""
        method = HTTP_CREATE_METHOD
        url_path = self.service_path + "/" + resource_path
        headers = self._setup_req_headers(tenant_id)
        if isinstance(object_data, str):
            request_body = object_data
        else:
            obj_dict = {object_name: object_data}
            request_body = self._tojson(obj_dict)

        try:
            response_status, resp_dict = self._execute_request(method, 
                                                           url_path, 
                                                           headers, 
                                                           body=request_body)
            return response_status, resp_dict
        except (LookupError, ImportError):
            exc_type, exc_value, exc_traceback = sys.exc_info()
            msg = _("Error while connecting to %(uri)s :  %(exception)s")
            LOG.error(msg % {"uri": self.uri,
                             "exception": exc_type})
            raise q_exc.ServiceUnavailable()

    def retrieve_resource(self, tenant_id, resource_path, parse_response=True):
        """Retrieves an HTTP REST resource of the NetScaler Control Center."""
        method = HTTP_READ_METHOD
        url_path = self.service_path + "/" + resource_path
        headers = self._setup_req_headers(tenant_id)

        try:
            response_status, resp_dict = self._execute_request(method, 
                                                           url_path, 
                                                           headers)
        except (LookupError, ImportError):
            exc_type, exc_value, exc_traceback = sys.exc_info()
            msg = _("Error while connecting to %(uri)s :  "
                    "%(exception)s")
            LOG.error(msg % {"uri": self.uri,
                             "exception": exc_type})
            raise q_exc.ServiceUnavailable()

        return resp_dict['status'], resp_dict

    def update_resource(self, tenant_id, resource_path, object_name, object_data):
        """Updates an HTTP REST resource of the NetScaler Control Center."""
        method = HTTP_UPDATE_METHOD
        url_path = self.service_path + "/" + resource_path
        headers = self._setup_req_headers(tenant_id)
        if isinstance(object_data, str):
            request_body = object_data
        else:
            obj_dict = {object_name: object_data}
            request_body = self._tojson(obj_dict)

        try:
            response_status, resp_dict = self._execute_request(method, 
                                                           url_path, 
                                                           headers, 
                                                           body=request_body)
            return response_status, resp_dict
        except (LookupError, ImportError):
            exc_type, exc_value, exc_traceback = sys.exc_info()
            msg = _("Error while connecting to %(uri)s :  %(exception)s")
            LOG.error(msg % {"uri": self.uri,
                             "exception": exc_type})
            raise q_exc.ServiceUnavailable()

    def remove_resource(self, tenant_id, resource_path, parse_response=True):
        """Removes an HTTP REST resource of NetScaler Control Center."""
        method = HTTP_DELETE_METHOD
        url_path = self.service_path + "/" + resource_path
        headers = self._setup_req_headers(tenant_id)

        try:
            response_status, resp_dict = self._execute_request(method, 
                                                           url_path, 
                                                           headers)
            return response_status, resp_dict
        except (LookupError, ImportError):
            exc_type, exc_value, exc_traceback = sys.exc_info()
            msg = _("Error while connecting to %(uri)s :  %(exception)s")
            LOG.error(msg % {"uri": self.uri,
                             "exception": exc_type})
            raise q_exc.ServiceUnavailable()

    def _fromjson(self, payload):
        """Converts a json string into a python dictionary"""
        return json.loads(payload)

    def _tojson(self, obj_dict):
        """Converts a python dictionary into a json string"""
        return json.dumps(obj_dict)


    def _get_connection(self):
        if self.protocol == HTTP_SCHEME:
            connection = httplib.HTTPConnection(self.host, self.port)
        elif self.protocol == HTTPS_SCHEME:
            connection = httplib.HTTPSConnection(self.host, self.port)
        else:
            LOG.error(_("protocol unrecognized:%s"), self.protocol)
            raise q_exc.ServiceUnavailable()
        return connection

    def _is_valid_response(self, response_status):
        # startus is less than 400, the response is fine
        if response_status < httplib.BAD_REQUEST:
            return True
        else:
            return False

    def _setup_req_headers(self, tenant_id):
        headers = {}
        headers[ACCEPT_HEADER] = JSON_CONTENT_TYPE
        headers[CONTENT_TYPE_HEADER] = JSON_CONTENT_TYPE
        headers[DRIVER_HEADER] = DRIVER_HEADER_VALUE
        headers[TENANT_HEADER] = tenant_id
        headers[AUTH_HEADER] = self.auth
        return headers

    def _get_response_dict(self, response):
        response_status = response.status
        response_body = response.read()
        response_headers = response.getheaders()
        response_dict = {}
        response_dict['status'] = response_status
        response_dict['body'] = response_body
        response_dict['headers'] = response_headers
        if self._is_valid_response(response_status):
            if len(response_body) > 0:
                parsed_body = self._fromjson(response_body)
                response_dict['dict'] = parsed_body
        return response_dict

    def _parse_uri(self, uri):
        parts = urlparse.urlparse(uri)
        self.uri = uri
        host_port_parts = parts.netloc.split(':')
        self.port = None
        if len(host_port_parts) > 1:
            self.host = host_port_parts[0]
            self.port = host_port_parts[1]
        else:
            self.host = host_port_parts[0]
        if type(self.host).__name__ == 'unicode':
            self.host = self.host.encode('ascii', 'ignore')
        if self.port and type(self.port).__name__ == 'unicode':
            self.port = self.port.encode('ascii', 'ignore')
        if parts.scheme.lower() == "http":
            LOG.warn(_("Connection to NetScaler Control Center (NCC) and credentials "
                       "are sent in clear text 'http' !! Please use 'https' "
                       "scheme when configuring NCC URL for stronger security."))
            self.protocol = HTTP_SCHEME
            if not self.port:
                self.port = HTTP_DEFAULT_PORT
        elif parts.scheme.lower() == HTTPS_SCHEME:
            self.protocol = HTTPS_SCHEME
            if not self.port:
                self.port = HTTPS_DEFAULT_PORT
        else:
            LOG.error(_("scheme in uri is unrecognized:%s"), parts.scheme)
            raise q_exc.ServiceUnavailable()
        self.service_path = parts.path

    def _execute_request(self, method, url_path, headers, body=None):
            connection = self._get_connection()
            connection.request(method, url_path, headers=headers, body=body)
            response = connection.getresponse()
            connection.close()
            resp_dict = self._get_response_dict(response)
            LOG.debug(_("Response: %s"), resp_dict['body'])
            response_status = resp_dict['status']
            if str(response_status) == HTTP_AUTH_FAILURE_STATUSCODE:
                LOG.error(_("Unable to login.Invalid credentials passed "
                            "for host: %s."), self.host)
                raise q_exc.ServiceUnavailable()
            if not self._is_valid_response(response_status):
                msg = _("Failed to update %(url_path)s "
                        "in %(uri)s, status: %(response_status)s")
                LOG.error(msg % {"url_path": url_path,
                                 "uri": self.uri,
                                 "response_status": response_status})
                raise q_exc.ServiceUnavailable()

            return response_status, resp_dict

