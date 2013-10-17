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


import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import exc
from sqlalchemy.orm import scoped_session

from neutron.api.v2 import attributes as attr
from neutron.common import constants
from neutron.db import db_base_plugin_v2
from neutron.db import model_base
from neutron.db import models_v2
from neutron.db.loadbalancer import loadbalancer_db as lb_db
from neutron.db.loadbalancer import db_base_serviceplugin_v2 as svc_base_db
from neutron.services.loadbalancer.extensions import certificate as ext_cert
from neutron.services.loadbalancer import constants as lb_const
from neutron.openstack.common import uuidutils
from neutron.openstack.common import log as logging


LOG = logging.getLogger(__name__)


class Certificate(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    """Represents a v2 neutron security group."""

    name = sa.Column(sa.String(255))
    description = sa.Column(sa.String(255))


class CertificateVipBinding(model_base.BASEV2):
    """Represents binding between certificates and vips."""

    vip_id = sa.Column(sa.String(36),
                        sa.ForeignKey("vips.id",
                                      ondelete='CASCADE'),
                        primary_key=True)
    certificate_id = sa.Column(sa.String(36),
                                  sa.ForeignKey("certificates.id"),
                                  primary_key=True)

    # Add a relationship to the Vip model in order to instruct SQLAlchemy to
    # eagerly load the vip's certificate
    vips = orm.relationship(
        lb_db.Vip,
        backref=orm.backref("certificate_id",
                            lazy='joined', cascade='delete'))


class CertificateDbMixin(ext_cert.CertificatePluginBase):
    """Mixin class to add certificates to db_plugin_base_v2."""

    __native_bulk_support = True

    def create_certificate(self, context, certificate):
        """Create certificate.
        """
        cert = certificate['certificate']
        tenant_id = self._get_tenant_id_for_create(context, cert)


        with context.session.begin(subtransactions=True):
            certificate_db = Certificate(id=cert.get('id') or (
                                              uuidutils.generate_uuid()),
                                              description=cert['description'],
                                              tenant_id=tenant_id,
                                              name=cert['name'])
            context.session.add(certificate_db)

        return self._make_certificate_dict(certificate_db)

    def get_certificates(self, context, filters=None, fields=None,
                            sorts=None, limit=None,
                            marker=None, page_reverse=False):


        marker_obj = self._get_marker_obj(context, 'certificate', limit,
                                          marker)
        return self._get_collection(context,
                                    Certificate,
                                    self._make_certificate_dict,
                                    filters=filters, fields=fields,
                                    sorts=sorts,
                                    limit=limit, marker_obj=marker_obj,
                                    page_reverse=page_reverse)

    def get_certificates_count(self, context, filters=None):
        return self._get_collection_count(context, SecurityGroup,
                                          filters=filters)

    def get_certificate(self, context, id, fields=None, tenant_id=None):
        """Tenant id is given to handle the case when creating a certificate
           on behalf of another user.
        """

        if tenant_id:
            tmp_context_tenant_id = context.tenant_id
            context.tenant_id = tenant_id

        try:
            with context.session.begin(subtransactions=True):
                ret = self._make_certificate_dict(self._get_certificate(
                                                     context, id), fields)
        finally:
            if tenant_id:
                context.tenant_id = tmp_context_tenant_id

        return ret


    def _get_certificate(self, context, id):
        try:
            query = self._model_query(context, Certificate)
            cert = query.filter(Certificate.id == id).one()

        except exc.NoResultFound:
            raise ext_cert.CertificateNotFound(id=id)
        return cert

    def delete_certificate(self, context, id):
        filters = {'certificate_id': id}
        binding = self._get_vip_certificate_binding(context, filters)
        if binding:
            raise ext_cert.CertificateInUse(id=id)

        # confirm certificate exists
        cert = self._get_certificate(context, id)

        with context.session.begin(subtransactions=True):
            context.session.delete(cert)


    def update_certificate(self, context, id, certificate):
        cert = certificate['certificate']
        with context.session.begin(subtransactions=True):
            db_cert = self._get_certificate(context, id)

            db_cert.update(cert)

        return self._make_certificate_dict(db_cert)


    def _make_certificate_dict(self, certificate, fields=None):
        res = {'id': certificate['id'],
               'name': certificate['name'],
               'tenant_id': certificate['tenant_id'],
               'description': certificate['description']}

        return self._fields(res, fields)

    def _make_certificate_binding_dict(self, certificate, fields=None):
        res = {'vip_id': certificate['vip_id'],
               'certificate_id': certificate['certificate_id']}
        return self._fields(res, fields)

    def _create_vip_certificate_binding(self, context, vip_id,
                                            certificate_id):
        with context.session.begin(subtransactions=True):
            db = CertificateVipBinding(vip_id=vip_id,
                                          certificate_id=certificate_id)
            context.session.add(db)

    def _get_vip_certificate_binding(self, context,
                                          filters=None, fields=None):
        bindings = self._get_collection(context,
                                    CertificateVipBinding,
                                    self._make_certificate_binding_dict,
                                    filters=filters, fields=fields)

        if len(bindings) > 0:
           return bindings[0]

        return None


    def _delete_vip_certificate_binding(self, context, vip_id):
        query = self._model_query(context, CertificateVipBinding)
        bindings = query.filter(
            CertificateVipBinding.vip_id == vip_id)
        with context.session.begin(subtransactions=True):
            for binding in bindings:
                context.session.delete(binding)

    def _extend_vip_dict_certificate(self, vip_res, vip_db):
        # Certificate bindings will be retrieved from the sqlalchemy
        # model. As they're loaded eagerly with vips because of the
        # joined load they will not cause an extra query.

        vipcertbindings = vip_db.certificate_id

        if len(vipcertbindings) == 1:
            vip_res['certificate_id'] = vipcertbindings[0].certificate_id

        return vip_res

    # Register dict extend functions for vips
    svc_base_db.NeutronDbServicePluginV2.register_dict_extend_funcs(
        lb_const.VIPS, ['_extend_vip_dict_certificate'])


    def _process_vip_create_certificate(self, context, vip,
                                            certificate):


        LOG.debug(_("Created a VIP-Certificate binding for vip_id=%s cert_id=%s" %
                    (vip['id'], certificate['id'])))

        self._create_vip_certificate_binding(context, vip['id'],
                                             certificate['id'])

        vip['certificate_id'] = certificate['id']


    def _get_certificate_on_vip(self, context, vip):
        """Check that the certificate on vip belong to tenant.

        :returns: the certificate ID on vip belonging to tenant.
        """
        v = vip['vip']
        if not attr.is_attr_set(v.get(ext_cert.CERTIFICATE_ID)):
            return

        return self.get_certificate(context, v[ext_cert.CERTIFICATE_ID])



