# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2013 New Dream Network, LLC (DreamHost)
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

import httplib
import mock

from neutron.common import exceptions
from neutron.services.loadbalancer.drivers.netscaler import (
    ncc_client, netscaler_driver
    )
from neutron.services.loadbalancer.drivers.netscaler.ncc_client import NSClient
from neutron.tests.unit import testlib_api

NCC_CLIENT_CLASS = ('neutron.services.loadbalancer.drivers.'
                                'netscaler.ncc_client.'
                                'NSClient')

HTTP_POST = 'POST'
HTTP_PUT = 'PUT'
HTTP_DELETE = 'DELETE'

HTTP_STATUSCODE_SUCCESS = 201
HTTP_STATUSCODE_FAILURE = 404

TESTURI_SCHEME = 'https'
TESTURI_HOSTNAME = 'valid_servername.acme.com'
TESTURI_PORT = 4433
TESTURI_PATH = '/ncc_service/1.0'
TESTURI = '%s://%s:%s%s' % (TESTURI_SCHEME, TESTURI_HOSTNAME,
                             TESTURI_PORT, TESTURI_PATH)
TEST_USERNAME = 'user211'
TEST_PASSWORD = '@30xHl5cT'
TEST_TENANT_ID = '9c5245a2-0432-9d4c-4829-9bd7028603a1'
TESTVIP_ID = '52ab5d71-6bb2-457f-8414-22a4ba55efec'


class TestNSClient(testlib_api.WebTestCase):
    """A Unit test for the NetScaler NCC client module. This test mocks
       the http connection. """
    def setUp(self):
        self.log = mock.patch.object(ncc_client, 'LOG').start()
        super(TestNSClient, self).setUp()
        # mock the httplib.HTTPConnection class (REST client)
        connectionclass = 'httplib.HTTPConnection' \
                           if TESTURI_SCHEME == 'http' \
                           else 'httplib.HTTPSConnection'
        self.connection_mock_cls = mock.patch(connectionclass).start()
        self.addCleanup(mock.patch.stopall)

    def test_instantiate_nsclient_with_empty_uri(self):
        #setup test
        test_uri = ''
        test_username = TEST_USERNAME
        test_password = TEST_PASSWORD
        #call method under test and assert that it raises an exception
        self.assertRaises(Exception, NSClient,
                          test_uri, test_username,
                          test_password)

    def test_instantiate_nsclient_with_valid_uri(self):
        #setup test
        test_uri = TESTURI
        test_username = TEST_USERNAME
        test_password = TEST_PASSWORD

        #call method under test: A new instance of NSClient
        testclient = NSClient(test_uri, test_username, test_password)

        # assert that the URI has been parsed correctly
        assert(testclient.host == TESTURI_HOSTNAME)
        assert(testclient.port == str(TESTURI_PORT))
        assert(testclient.protocol == TESTURI_SCHEME)
        assert(testclient.service_path == TESTURI_PATH)

    def test_create_resource_with_no_connection(self):
        # mock a connection object that fails to establish a connection
        self.connection_mock_cls.side_effect = httplib.HTTPException()
        #setup test
        testclient = self._get_nsclient()
        resource_path = netscaler_driver.VIPS_RESOURCE
        resource_name = netscaler_driver.VIP_RESOURCE
        resource_body = self._get_testvip_httpbody_for_create()
        # call method under test: create_resource() and assert that
        # it raises an exception
        self.assertRaises(httplib.HTTPException, testclient.create_resource,
                          TEST_TENANT_ID, resource_path,
                          resource_name, resource_body)

    def test_create_resource_with_error(self):
        #create a mock object to represent a valid http response
        # with a failure status code.
        response_mock = mock.MagicMock()
        response_mock.status = HTTP_STATUSCODE_FAILURE
        response_mock.read.return_value = ''
        response_mock.getheaders.return_value = []
        # mock the getresponse() method of httplib.HTTPConnection class
        # to return the object above.
        connection_instance = self.connection_mock_cls.return_value
        connection_instance.getresponse.return_value = response_mock
        #set up the test
        testclient = self._get_nsclient()
        resource_path = netscaler_driver.VIPS_RESOURCE
        resource_name = netscaler_driver.VIP_RESOURCE
        resource_body = self._get_testvip_httpbody_for_create()
        # call method under test: create_resource
        # and assert that it raises the expected exception.
        self.assertRaises(exceptions.ServiceUnavailable,
                          testclient.create_resource,
                          TEST_TENANT_ID, resource_path,
                          resource_name, resource_body)

    def test_create_resource(self):
        # create a mock object to represent a valid http response
        # with a success status code.
        response_mock = mock.MagicMock()
        response_mock.status = HTTP_STATUSCODE_SUCCESS
        response_mock.read.return_value = ''
        response_mock.getheaders.return_value = []
        # mock the getresponse() method of httplib.HTTPConnection class
        # to return the object above.
        connection_instance = self.connection_mock_cls.return_value
        connection_instance.getresponse.return_value = response_mock
        # obtain the mock object that corresponds to the call of request()
        # on httplib.HTTPConnection
        request_method_mock = self.connection_mock_cls.return_value.request
        #set up the test
        testclient = self._get_nsclient()
        resource_path = netscaler_driver.VIPS_RESOURCE
        resource_name = netscaler_driver.VIP_RESOURCE
        resource_body = self._get_testvip_httpbody_for_create()
        # call method under test: create_resource()
        testclient.create_resource(TEST_TENANT_ID, resource_path,
                                   resource_name, resource_body)
        # assert that httplib.HTTPConnection request() was called with the
        # expected params
        path = "%s/%s" % (testclient.service_path,  resource_path)
        request_method_mock.assert_called_once_with(HTTP_POST,
                                                    path,
                                                    body=mock.ANY,
                                                    headers=mock.ANY)

    def test_update_resource_with_error(self):
        #create a mock object to represent a valid http response
        response_mock = mock.MagicMock()
        response_mock.status = HTTP_STATUSCODE_FAILURE
        response_mock.read.return_value = ''
        response_mock.getheaders.return_value = []
        # mock the getresponse() method of httplib.HTTPConnection class
        # to return the object above.
        connection_instance = self.connection_mock_cls.return_value
        connection_instance.getresponse.return_value = response_mock
        #set up the test
        testclient = self._get_nsclient()
        resource_path = "%s/%s" % (netscaler_driver.VIPS_RESOURCE,
                                   TESTVIP_ID)
        resource_name = netscaler_driver.VIP_RESOURCE
        resource_body = self._get_testvip_httpbody_for_update()
        # call method under test: update_resource() and
        # assert that it raises the expected exception.
        self.assertRaises(exceptions.ServiceUnavailable,
                          testclient.update_resource,
                          TEST_TENANT_ID, resource_path,
                          resource_name, resource_body)

    def test_update_resource(self):
        #create a mock object to represent a valid http response
        response_mock = mock.MagicMock()
        response_mock.status = HTTP_STATUSCODE_SUCCESS
        response_mock.read.return_value = ''
        response_mock.getheaders.return_value = []
        # mock the getresponse() method of httplib.HTTPConnection class
        # to return the object above.
        connection_instance = self.connection_mock_cls.return_value
        connection_instance.getresponse.return_value = response_mock
        # obtain the mock object that corresponds to the call of request()
        # on httplib.HTTPConnection.
        request_method_mock = self.connection_mock_cls.return_value.request
        #set up the test.
        testclient = self._get_nsclient()
        resource_path = "%s/%s" % (netscaler_driver.VIPS_RESOURCE,
                                   TESTVIP_ID)
        resource_name = netscaler_driver.VIP_RESOURCE
        resource_body = self._get_testvip_httpbody_for_update()
        # call method under test: update_resource.
        testclient.update_resource(TEST_TENANT_ID, resource_path,
                                   resource_name, resource_body)
        path = "%s/%s" % (testclient.service_path,  resource_path)
        # assert that httplib.HTTPConnection request() was called with the
        # expected params.
        request_method_mock.assert_called_once_with(HTTP_PUT,
                                                    path,
                                                    body=mock.ANY,
                                                    headers=mock.ANY)

    def test_delete_resource_with_error(self):
        #create a mock object to represent a valid http response
        response_mock = mock.MagicMock()
        response_mock.status = HTTP_STATUSCODE_FAILURE
        response_mock.read.return_value = ''
        response_mock.getheaders.return_value = []
        # mock the getresponse() method of httplib.HTTPConnection class
        # to return the object above.
        connection_instance = self.connection_mock_cls.return_value
        connection_instance.getresponse.return_value = response_mock
        #set up the test
        testclient = self._get_nsclient()
        resource_path = "%s/%s" % (netscaler_driver.VIPS_RESOURCE,
                                   TESTVIP_ID)
        # call method under test: create_resource
        self.assertRaises(exceptions.ServiceUnavailable,
                          testclient.remove_resource,
                          TEST_TENANT_ID, resource_path)

    def test_delete_resource(self):
        #create a mock object to represent a valid http response
        response_mock = mock.MagicMock()
        response_mock.status = HTTP_STATUSCODE_SUCCESS
        response_mock.read.return_value = ''
        response_mock.getheaders.return_value = []
        # mock the getresponse() method of httplib.HTTPConnection class
        # to return the object above.
        connection_instance = self.connection_mock_cls.return_value
        connection_instance.getresponse.return_value = response_mock
        # obtain the mock object that corresponds to the call of request()
        # on httplib.HTTPConnection
        request_method_mock = self.connection_mock_cls.return_value.request
        #set up the test
        testclient = self._get_nsclient()
        resource_path = "%s/%s" % (netscaler_driver.VIPS_RESOURCE,
                                   TESTVIP_ID)
        path = "%s/%s" % (testclient.service_path,  resource_path)
        # call method under test: create_resource
        testclient.remove_resource(TEST_TENANT_ID, resource_path)
        # assert that httplib.HTTPConnection request() was called with the
        # expected params
        request_method_mock.assert_called_once_with(HTTP_DELETE,
                                                    path,
                                                    body=mock.ANY,
                                                    headers=mock.ANY)

    def _get_nsclient(self):
        test_uri = TESTURI
        test_username = TEST_USERNAME
        test_password = TEST_PASSWORD
        return NSClient(test_uri, test_username, test_password)

    def _get_testvip_httpbody_for_create(self):
        body = {
                'name': 'vip1',
                'address': '10.0.0.3',
                'pool_id': 'da477c13-24cd-4c9f-8c19-757a61ef3b9d',
                'protocol': 'HTTP',
                'protocol_port': 80,
                'admin_state_up': True,
        }
        return body

    def _get_testvip_httpbody_for_update(self):
        body = {}
        body['name'] = 'updated vip1'
        body['admin_state_up'] = False
        return body
