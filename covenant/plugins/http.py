# -*- coding: utf-8 -*-
"""http plugin"""

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
import requests

from covenant.classes.plugins import CovenantPlugBase, PLUGINS

LOG = logging.getLogger('covenant.plugins.http')


class CovenantHttpPlugin(CovenantPlugBase):
    PLUGIN_NAME = 'http'

    def do_metrics(self, obj):
        for target in self.targets:
            cfg  = target.config
            req  = None
            auth = None

            if target.credentials:
                auth = (target.credentials['username'],
                        target.credentials['password'])

            try:
                req = requests.get(cfg['uri'],
                                   auth    = auth,
                                   timeout = cfg['timeout'])

                if req.status_code != requests.codes.ok:
                    raise LookupError("invalid status code: %r. (error: %r)" % (req.status_code, req.text))

                if cfg.get('format') == 'json':
                    data = req.json()
                else:
                    data = req.text
            except Exception:
                raise
            finally:
                if req:
                    req.close()

            target(data)

        return self.generate_latest()


if __name__ != "__main__":
    def _start():
        PLUGINS.register(CovenantHttpPlugin)
    _start()
