# -*- coding: utf-8 -*-
# Copyright (C) 2018-2021 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.plugins.predis"""

import logging
import redis

from covenant.classes.exceptions import CovenantConfigurationError
from covenant.classes.plugins import CovenantPlugBase, CovenantTargetFailed, PLUGINS

LOG = logging.getLogger('covenant.plugins.redis')

_ALLOWED_COMMANDS = ('client_list',
                     'config_get',
                     'info',
                     'llen')


class CovenantRedisPlugin(CovenantPlugBase):
    PLUGIN_NAME = 'redis'

    def _do_call(self, obj, targets = None, registry = None): # pylint: disable=unused-argument
        if not targets:
            targets = self.targets

        param_target = obj.get_params().get('target')

        for target in targets:
            (data, conn) = (None, None)
            command      = 'info'
            command_args = []
            cfg          = target.config

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
                    cfg['url'] = param_target

                if cfg.get('url'):
                    conn = redis.from_url(**cfg)
                else:
                    conn = redis.Redis(**cfg)

                data = getattr(conn, command)(*command_args)
            except Exception as e:
                data = CovenantTargetFailed(e)
                LOG.exception("error on target: %r. exception: %r",
                              target.name,
                              e)

            target(data)

        return self.generate_latest(registry)


if __name__ != "__main__":
    def _start():
        PLUGINS.register(CovenantRedisPlugin)
    _start()
