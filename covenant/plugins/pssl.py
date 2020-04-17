# -*- coding: utf-8 -*-
# Copyright (C) 2020 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.plugins.pssl"""

import logging
import socket
import ssl

from datetime import datetime

from cryptography import x509
from cryptography.hazmat.backends import default_backend

import six

from sonicprobe.libs import network, urisup

from covenant.classes.exceptions import CovenantConfigurationError
from covenant.classes.plugins import CovenantPlugBase, CovenantTargetFailed, PLUGINS

LOG = logging.getLogger('covenant.plugins.ssl')

_ALLOWED_OPTIONS = ('ALL',
                    'NO_SSLv2',
                    'NO_SSLv3',
                    'NO_TLSv1',
                    'NO_TLSv1_1',
                    'NO_TLSv1_2',
                    'NO_TLSv1_3',
                    'NO_COMPRESSION',
                    'CIPHER_SERVER_PREFERENCE',
                    'SINGLE_DH_USE',
                    'SINGLE_ECDH_USE',
                    'ENABLE_MIDDLEBOX_COMPAT')

_IP_PROTOCOLS    = {'ipv4': socket.AF_INET,
                    'ipv6': socket.AF_INET6}


class CovenantSslPlugin(CovenantPlugBase):
    PLUGIN_NAME = 'ssl'

    @staticmethod
    def _dnsname_to_idn(name):
        for x in ('*.', '.'):
            if name.startswith(x):
                return "%s%s" % (x, network.encode_idn(name[len(x):], True))

        return network.encode_idn(name, True)

    @staticmethod
    def _valid_hostname(valid_hosts, host):
        try:
            ssl.match_hostname(valid_hosts, host)
        except ssl.CertificateError:
            return False

        return True

    @staticmethod
    def _load_cert(cert_der, rs = None):
        if not isinstance(rs, dict):
            rs = {}

        cert = x509.load_der_x509_certificate(six.ensure_str(cert_der), default_backend())

        rs['connect_success'] = True
        rs['cert_not_before'] = int(cert.not_valid_before.strftime('%s'))
        rs['cert_not_after'] = int(cert.not_valid_after.strftime('%s'))
        rs['cert_has_expired'] = cert.not_valid_after < datetime.utcnow()
        rs['cert_serial_no'] = cert.serial_number
        rs['cert_issuer_cn'] = cert.issuer.get_attributes_for_oid(x509.OID_COMMON_NAME)[0].value
        rs['cert_cn'] = cert.subject.get_attributes_for_oid(x509.OID_COMMON_NAME)[0].value
        rs['cert_emails'] = []
        rs['cert_dns_names'] = []
        rs['cert_ip_addresses'] = []

        for x in cert.subject.get_attributes_for_oid(x509.OID_EMAIL_ADDRESS):
            rs['cert_emails'].append(six.ensure_str(x.value))

        rs['cert_ou'] = []
        for x in cert.subject.get_attributes_for_oid(x509.OID_ORGANIZATIONAL_UNIT_NAME):
            rs['cert_ou'].append(six.ensure_str(x.value))

        return (cert, rs)

    @staticmethod
    def _load_context_options(context, options):
        if not isinstance(options, list):
            return

        for x in options:
            if x not in _ALLOWED_OPTIONS:
                LOG.warning("invalid ssl option: OP_%s", x)
                continue

            if not hasattr(ssl, "OP_%s" % x):
                LOG.warning("unknown ssl option: OP_%s", x)
                continue

            context.options |= getattr(ssl, "OP_%s" % x)

    @staticmethod
    def _connect(context, host, port, server_hostname, ip_protocol, timeout):
        conn = context.wrap_socket(
            socket.socket(ip_protocol),
            server_hostname = server_hostname)

        conn.settimeout(timeout)
        conn.connect((host, int(port)))

        return conn

    def _subject_alt_name(self, cert, rs = None, valid_hosts = None):
        if not isinstance(rs, dict):
            rs = {}

        if not isinstance(valid_hosts, dict):
            valid_hosts = {}

        try:
            ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        except Exception:
            return (rs, valid_hosts)

        for x in ext.value:
            if isinstance(x, x509.RFC822Name):
                rs['cert_emails'].append(six.ensure_str(x.value))
            elif isinstance(x, x509.DNSName):
                rs['cert_dns_names'].append(six.ensure_str(x.value))
                valid_hosts['subjectAltName'].append(('DNS', self._dnsname_to_idn(x.value)))
            elif isinstance(x, x509.IPAddress):
                rs['cert_ip_addresses'].append(six.ensure_str(x.value.compressed))
                valid_hosts['subjectAltName'].append(('IP Address', six.ensure_str(x.value.compressed)))

        return (rs, valid_hosts)

    def _do_call(self, obj, targets = None, registry = None): # pylint: disable=unused-argument
        if not targets:
            targets = self.targets

        for target in targets:
            (data, conn)       = (None, None)

            cfg                = target.config
            common_name        = cfg.get('common_name')
            cfg['verify_peer'] = cfg.get('verify_peer', True)
            cfg['ip_protocol'] = _IP_PROTOCOLS.get(cfg.get('ip_protocol'), socket.AF_INET)

            if cfg.get('timeout') is not None:
                cfg['timeout'] = float(cfg['timeout'])
            else:
                cfg['timeout'] = None

            params             = obj.get_params()

            if not params.get('target'):
                uri = cfg.get('uri')
            else:
                uri = params['target']

            if not uri:
                raise CovenantConfigurationError("missing target or uri in configuration")

            uri_split          = urisup.uri_help_split(uri)
            scheme             = None

            if not isinstance(uri_split[1], tuple):
                host = uri_split[0]
                port = uri_split[2]
            elif uri_split[1]:
                scheme     = uri_split[0]
                host, port = uri_split[1][2:4]
            else:
                raise CovenantConfigurationError("missing host and port in uri: %r" % uri)

            if not host:
                raise CovenantConfigurationError("missing or invalid host in uri: %r" % uri)

            if scheme and not port:
                try:
                    port = socket.getservbyname(scheme)
                except socket.error:
                    pass

            if not port:
                raise CovenantConfigurationError("missing or invalid port in uri: %r" % uri)

            data = {'connect_success': False,
                    'cert_secure': False,
                    "%s_success" % self.type: False}

            conn = None

            try:
                server_hostname = common_name or host

                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

                self._load_context_options(context, cfg.get('options'))

                conn = self._connect(context,
                                     host,
                                     port,
                                     server_hostname,
                                     cfg['ip_protocol'],
                                     cfg['timeout'])

                data['cipher_info'] = conn.cipher()[0]
                data['version_info'] = conn.version()

                valid_hosts = {'subject': [],
                               'subjectAltName': []}

                cert_der = conn.getpeercert(True)
                if cert_der:
                    self._subject_alt_name(self._load_cert(cert_der, data)[0], data, valid_hosts)
                    data['hostname_valid'] = self._valid_hostname(valid_hosts, server_hostname)

                    if cfg['verify_peer']:
                        if conn:
                            conn.shutdown(socket.SHUT_RDWR)
                            conn.close()
                            conn = None

                        context.verify_mode = ssl.CERT_REQUIRED
                        context.load_default_certs(ssl.Purpose.SERVER_AUTH)
                        conn = self._connect(context,
                                             host,
                                             port,
                                             server_hostname,
                                             cfg['ip_protocol'],
                                             cfg['timeout'])
            except ssl.SSLError as e:
                LOG.warning("ssl error on target: %r. exception: %r",
                            target.name,
                            e)
            except Exception as e:
                data = CovenantTargetFailed(e)
                LOG.exception("error on target: %r. exception: %r",
                              target.name,
                              e)
            else:
                if data.get('connect_success'):
                    if not cfg['verify_peer']:
                        data["%s_success" % self.type] = True
                    elif not data.get('cert_has_expired') \
                       and data.get('hostname_valid'):
                        data['cert_secure'] = True
                        data["%s_success" % self.type] = True
            finally:
                if conn:
                    conn.shutdown(socket.SHUT_RDWR)
                    conn.close()

            target(data)

        return self.generate_latest(registry)


if __name__ != "__main__":
    def _start():
        PLUGINS.register(CovenantSslPlugin)
    _start()
