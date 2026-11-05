# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.plugins.predis"""

import logging
import re
import redis

from covenant.classes.exceptions import CovenantConfigurationError
from covenant.classes.plugins import CovenantPlugBase, CovenantTargetFailed, PLUGINS

from covenant.services.credential_targets import RedisCredentialTargets

LOG = logging.getLogger('covenant.plugins.redis')

_ALLOWED_COMMANDS = ('client_list',
                     'config_get',
                     'info',
                     'llen')


# A caller supplies only a network destination and an optional database number.
_DYNAMIC_URL = re.compile(r'\A(rediss?)://(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9._-]+)'
                          r'(?::([0-9]+))?(?:/([0-9]*))?\Z')
_CREDENTIAL_OPTIONS = ('username', 'password', 'credential_provider',
                       'ssl_keyfile', 'ssl_certfile', 'ssl_password',
                       'ssl_ocsp_context', 'ssl_ocsp_expected_cert')


def _dynamic_url(value):
    match = _DYNAMIC_URL.match(value)
    if not match:
        raise ValueError('expected redis:// or rediss:// host with optional port and /database')
    scheme, host, port, database = match.groups()
    port = int(port) if port else RedisCredentialTargets.DEFAULT_PORTS[scheme]
    if not 1 <= port <= 65535:
        raise ValueError('invalid Redis port')
    # Use the same explicit destination for matching and for redis-py. Otherwise
    # a configured port could override the implicit port of the caller's URL.
    origin = '%s://%s:%d' % (scheme, host, port)
    return origin + ('/' + database if database else '')


class CovenantRedisPlugin(CovenantPlugBase):
    PLUGIN_NAME = 'redis'

    def safe_init(self):
        RedisCredentialTargets.load_imports(self.config)
        super(CovenantRedisPlugin, self).safe_init()
        for target in self.targets:
            RedisCredentialTargets(target.config.get('credential_targets', []))

    def _do_call(self, obj, targets = None, registry = None): # pylint: disable=unused-argument
        if not targets:
            targets = self.targets

        param_target = obj.get_params().get('target')

        for target in targets:
            (data, conn) = (None, None)
            command      = 'info'
            command_args = []
            cfg          = target.config
            rules        = cfg.pop('credential_targets', [])

            for x in ('socket_timeout', 'socket_connect_timeout'):
                if cfg.get(x) is not None:
                    cfg[x] = float(cfg[x])
                else:
                    cfg[x] = None

            if 'command' in cfg:
                command = cfg.pop('command').lower()

            if 'command_args' in cfg:
                command_args = list(cfg.pop('command_args') or [])

            if command not in _ALLOWED_COMMANDS:
                raise CovenantConfigurationError("invalid redis command: %r" % command)

            if target.credentials:
                cfg['username'] = target.credentials['username']
                cfg['password'] = target.credentials['password']

            try:
                if param_target and not cfg.get('url'):
                    cfg['url'] = _dynamic_url(param_target)
                    if not RedisCredentialTargets(rules).allows(cfg['url']):
                        for option in _CREDENTIAL_OPTIONS:
                            cfg.pop(option, None)

                if cfg.get('url'):
                    conn = redis.from_url(**cfg)
                else:
                    conn = redis.Redis(**cfg)

                data = getattr(conn, command)(*command_args)
            except Exception as e:
                data = CovenantTargetFailed(e)
                LOG.error("target %r failed: %s", target.name, type(e).__name__)

            target(data)

        return self.generate_latest(registry)


if __name__ != "__main__":
    def _start():
        PLUGINS.register(CovenantRedisPlugin)
    _start()
