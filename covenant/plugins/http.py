# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.plugins.http"""

from functools import partial
import logging
import math
import os
import requests
import six
import yaml

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


DEFAULT_HTTP_TIMEOUT = 10
DEFAULT_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
READ_CHUNK_BYTES = 16 * 1024


def _response_limits(cfg):
    value = cfg.get('timeout')
    try:
        timeout = DEFAULT_HTTP_TIMEOUT if value is None else float(value)
        if isinstance(value, bool) or timeout <= 0 or math.isnan(timeout) or math.isinf(timeout):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise CovenantConfigurationError('HTTP timeout must be positive and finite')
    limit = cfg.get('max_response_bytes', DEFAULT_MAX_RESPONSE_BYTES)
    if isinstance(limit, bool) or not isinstance(limit, six.integer_types) or limit <= 0:
        raise CovenantConfigurationError('max_response_bytes must be a positive integer')
    return timeout, limit


def _buffer_response(limit, response, **kwargs):
    # Requests consumes redirect bodies internally, even with stream=True.
    # Cache only the successful payload before its redirect or decoding logic runs.
    try:
        body = bytearray()
        if response.status_code == requests.codes['ok']:
            for chunk in response.iter_content(min(READ_CHUNK_BYTES, limit + 1)):
                if len(body) + len(chunk) > limit:
                    raise ValueError('HTTP response exceeds max_response_bytes')
                body.extend(chunk)
        response._content = bytes(body)
    finally:
        response.close()
    return response


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
        for target in self.config.get('metrics', []) + self.config.get('probes', []):
            cfg = target.get('config')
            if isinstance(cfg, dict) and 'import_credential_targets' in cfg:
                self._import_credential_targets(cfg)
        super(CovenantHttpPlugin, self).safe_init()
        for target in self.targets:
            _response_limits(target.config)
            CredentialTargets(target.config.get('credential_targets', []))

    def _import_credential_targets(self, cfg):
        source = cfg['import_credential_targets']
        if not isinstance(source, six.string_types) or not source.strip() or '\x00' in source:
            raise CovenantConfigurationError('import_credential_targets requires a YAML file path')
        path = os.path.join(self.config['covenant']['config_dir'], source)
        try:
            with open(path, 'rb') as stream:
                imported = yaml.safe_load(stream)
        except (IOError, OSError, yaml.YAMLError, UnicodeError):
            raise CovenantConfigurationError('cannot read import_credential_targets file %r' % source)

        inline = cfg.get('credential_targets', [])
        if not isinstance(imported, list) or not isinstance(inline, list):
            raise CovenantConfigurationError('imported and inline credential_targets must be lists')
        rules = imported + inline
        CredentialTargets(rules)
        cfg['credential_targets'] = rules
        del cfg['import_credential_targets']

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

            cfg['timeout'], limit = _response_limits(cfg)
            cfg.pop('max_response_bytes', None)
            cfg['stream'] = True
            hooks = requests.Request(hooks=cfg.get('hooks')).hooks
            hooks['response'].insert(0, partial(_buffer_response, limit))
            cfg['hooks'] = hooks

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
                    raise LookupError("upstream HTTP status %d" % req.status_code)

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
                if req is not None:
                    req.close()

            target(data)

        return self.generate_latest(registry)


if __name__ != "__main__":
    def _start():
        PLUGINS.register(CovenantHttpPlugin)
    _start()
