# -*- coding: utf-8 -*-
"""covenant plugin redis"""

__author__  = "Adrien DELLE CAVE"
__license__ = """
    Copyright (C) 2018  doowan

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA..
"""

import logging
import redis

from covenant.classes.plugins import CovenantPlugBase, CovenantTargetFailed, PLUGINS

LOG = logging.getLogger('covenant.plugins.redis')

_ALLOWED_COMMANDS = ('info', 'config_get')


class CovenantRedisPlugin(CovenantPlugBase):
    PLUGIN_NAME = 'redis'

    def do_metrics(self, obj):
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
                raise CovenantConfigurationError("invalid redis command: %r" % cmd)

            if target.credentials:
                cfg['username'] = target.credentials['username']
                cfg['password'] = target.credentials['password']

            try:
                if 'url' in cfg:
                    conn = redis.from_url(**cfg)
                else:
                    conn = redis.Redis(**cfg)

                data = getattr(conn, command)(*command_args)
            except Exception, e:
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
