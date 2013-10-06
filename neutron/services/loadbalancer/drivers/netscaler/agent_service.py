# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 Nicira Networks, Inc
# All Rights Reserved.
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

import inspect
import logging as std_logging
import os
import random

from oslo.config import cfg

from neutron.common import config
from neutron.common import legacy
from neutron import context
from neutron.openstack.common import importutils
from neutron.openstack.common import log as logging
from neutron.openstack.common import loopingcall
from neutron.openstack.common.rpc import service
from neutron import wsgi


service_opts = [
    cfg.IntOpt('periodic_interval',
               default=40,
               help=_('Seconds between running periodic tasks')),
    cfg.IntOpt('periodic_fuzzy_delay',
               default=5,
               help=_('range of seconds to randomly delay when starting the'
                      ' periodic task scheduler to reduce stampeding.'
                      ' (Disable by setting to 0)')),
]
CONF = cfg.CONF
CONF.register_opts(service_opts)

LOG = logging.getLogger(__name__)


class WsgiService(object):
    """Base class for WSGI based services.

    For each api you define, you must also define these flags:
    :<api>_listen: The address on which to listen
    :<api>_listen_port: The port on which to listen

    """

    def __init__(self, app_name):
        self.app_name = app_name
        self.wsgi_app = None

    def start(self):
        self.wsgi_app = _run_wsgi(self.app_name)

    def wait(self):
        self.wsgi_app.wait()



class LBaaSAgentApiService(WsgiService):
    """Class for lbaas-agent service."""

    @classmethod
    def create(cls, app_name='lbaas-agent'):

        # Setup logging early, supplying both the CLI options and the
        # configuration mapping from the config file
        # We only update the conf dict for the verbose and debug
        # flags. Everything else must be set up in the conf file...
        # Log the options used when starting if we're in debug mode...

        config.setup_logging(cfg.CONF)
        # Dump the initial option values
        cfg.CONF.log_opt_values(LOG, std_logging.DEBUG)
        service = cls(app_name)
        return service

def serve_wsgi(cls):

    try:
        service = cls.create()
        service.start()
    except Exception:
        LOG.exception(_('In serve_wsgi()'))
        raise

    return service


def _run_wsgi(app_name):
    LOG.debug(_("Loading paste app %s" % app_name))
    app = config.load_paste_app(app_name)
    if not app:
        LOG.error(_('No known API applications configured.'))
        return
    server = wsgi.Server("LBaaS-agent")
    server.start(app, cfg.CONF.agent_bind_port, cfg.CONF.agent_bind_host)
    # Dump all option values here after all options are parsed
    cfg.CONF.log_opt_values(LOG, std_logging.DEBUG)
    LOG.info(_("Loading paste app %s" % app_name))
    LOG.info(_("LBaaS-agent service started, listening on %(host)s:%(port)s"),
             {'host': cfg.CONF.agent_bind_host,
              'port': cfg.CONF.agent_bind_port})
    return server


