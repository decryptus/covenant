# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.plugins.http"""

import logging
import requests

from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

from sonicprobe.libs import urisup

from covenant.classes.exceptions import CovenantConfigurationError
from covenant.classes.plugins import CovenantPlugBase, CovenantTargetFailed, PLUGINS

from covenant.services.credential_targets import CredentialTargets

LOG = logging.getLogger('covenant.plugins.http')

_ALLOWED_METHODS = ('delete',
                    'get',
                    'head',
                    'patch',
                    'post',
                    'put')


class CredentialAdapter(HTTPAdapter):
    """Apply configured credentials to each prepared URL, including redirects."""
    def __init__(self, policy, cfg):
        super(CredentialAdapter, self).__init__()
        self.policy = policy
        self.configured_headers = cfg.pop('headers') or {}
        self.configured_auth = cfg.pop('auth', None)
        self.configured_cert = cfg.pop('cert', None)

    def send(self, request, **kwargs):
        outgoing = request.copy()
        if self.policy.allows(outgoing.url):
            outgoing.headers.update(self.configured_headers)
            if self.configured_auth:
                HTTPBasicAuth(*self.configured_auth)(outgoing)
            kwargs['cert'] = self.configured_cert
        else:
            for header in ('Authorization', 'Cookie', 'Proxy-Authorization'):
                outgoing.headers.pop(header, None)
            kwargs['cert'] = None
        return super(CredentialAdapter, self).send(outgoing, **kwargs)


class CovenantHttpPlugin(CovenantPlugBase):
    PLUGIN_NAME = 'http'

    def safe_init(self):
        super(CovenantHttpPlugin, self).safe_init()
        for target in self.targets:
            CredentialTargets(target.config.get('credential_targets', []))

    def _do_call(self, obj, targets = None, registry = None): # pylint: disable=unused-argument
        if not targets:
            targets = self.targets

        param_target = obj.get_params().get('target')

        for target in targets:
            (data, req) = (None, None)

            cfg         = target.config
            method      = 'get'
            xformat     = None

            if 'format' in cfg:
                xformat = cfg.pop('format').lower()

            if 'uri' in cfg and not cfg.get('url'):
                cfg['url'] = cfg.pop('uri')

            dynamic = not cfg.get('url')
            rules = cfg.pop('credential_targets', None)
            if param_target and dynamic:
                cfg['url'] = param_target

            if not cfg.get('url'):
                raise CovenantConfigurationError("missing uri or target in configuration")

            if 'path' in cfg:
                url = list(urisup.uri_help_split(cfg['url']))
                if url[2]:
                    url[2] = "%s/%s" % (url[2].rstrip('/'), cfg.pop('path', '').lstrip('/'))
                else:
                    url[2] = cfg.pop('path')
                cfg['url'] = urisup.uri_help_unsplit(url)

            if 'method' in cfg:
                method = cfg.pop('method').lower()

            if 'ssl_verify' in cfg:
                cfg['verify'] = bool(cfg.pop('ssl_verify'))

            if cfg.get('timeout') is not None:
                cfg['timeout'] = float(cfg['timeout'])
            else:
                cfg['timeout'] = None

            if not isinstance(cfg.get('headers'), dict):
                cfg['headers'] = None

            if target.credentials:
                cfg['auth'] = (target.credentials['username'],
                               target.credentials['password'])

            if method not in _ALLOWED_METHODS:
                raise CovenantConfigurationError("invalid http method: %r" % method)

            try:
                if dynamic or rules is not None:
                    with requests.Session() as session:
                        session.trust_env = False
                        adapter = CredentialAdapter(CredentialTargets(rules or []), cfg)
                        session.mount('http://', adapter)
                        session.mount('https://', adapter)
                        cfg.setdefault('allow_redirects', method != 'head')
                        req = session.request(method, **cfg)
                else:
                    req = getattr(requests, method)(**cfg)

                if req.status_code != requests.codes['ok']:
                    raise LookupError("invalid status code: %r. (error: %r)"
                                      % (req.status_code, req.text))

                if xformat == 'json':
                    data = req.json()
                else:
                    data = req.text
            except Exception as e:
                data = CovenantTargetFailed(e)
                LOG.exception("error on target: %r. exception: %r",
                              target.name,
                              e)
            finally:
                if req:
                    req.close()

            target(data)

        return self.generate_latest(registry)


if __name__ != "__main__":
    def _start():
        PLUGINS.register(CovenantHttpPlugin)
    _start()
