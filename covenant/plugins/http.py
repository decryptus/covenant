# -*- coding: utf-8 -*-
# Copyright (C) 2018-2021 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.plugins.http"""

import logging
import requests

from sonicprobe.libs import urisup

from covenant.classes.exceptions import CovenantConfigurationError
from covenant.classes.plugins import CovenantPlugBase, CovenantTargetFailed, PLUGINS

LOG = logging.getLogger('covenant.plugins.http')

_ALLOWED_METHODS = ('delete',
                    'get',
                    'head',
                    'patch',
                    'post',
                    'put')


class CovenantHttpPlugin(CovenantPlugBase):
    PLUGIN_NAME = 'http'

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

            if param_target and not cfg.get('url'):
                cfg['url'] = param_target

            if not cfg.get('url'):
                raise CovenantConfigurationError("missing uri or target in configuration")

            if 'path' in cfg:
                url = list(urisup.uri_help_split(cfg['url']))
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
