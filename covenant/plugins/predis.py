# -*- coding: utf-8 -*-
# Copyright (C) 2018-2019 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.plugins.predis"""

import logging
import redis

from covenant.classes.exceptions import CovenantConfigurationError
from covenant.classes.plugins import CovenantPlugBase, CovenantTargetFailed, PLUGINS

LOG = logging.getLogger('covenant.plugins.redis')

_ALLOWED_COMMANDS = ('info', 'config_get')


class CovenantRedisPlugin(CovenantPlugBase):
    PLUGIN_NAME = 'redis'

    def do_metrics(self, obj): # pylint: disable=unused-argument
        for target in self.targets:
            (data, conn) = (None, None)
            command                       = 'info'
            command_args                  = []
            cfg                           = target.config
            cfg['socket_timeout']         = cfg.get('socket_timeout', 10)
            cfg['socket_connect_timeout'] = cfg.get('socket_connect_timeout', 10)

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
                if 'url' in cfg:
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

        return self.generate_latest()


if __name__ != "__main__":
    def _start():
        PLUGINS.register(CovenantRedisPlugin)
    _start()
