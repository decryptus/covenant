# -*- coding: utf-8 -*-
"""covenant configuration"""

__author__  = "Adrien DELLE CAVE <adc@doowan.net>"
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
import os
import signal
import yaml

from covenant.classes.plugins import ENDPOINTS, PLUGINS
from dwho.config import parse_conf, stop, DWHO_THREADS
from dwho.classes.libloader import DwhoLibLoader
from dwho.classes.modules import MODULES
from mako.template import Template
from sonicprobe.helpers import load_yaml
from sonicprobe.libs.http_json_server import get_default_options

_TPL_IMPORTS = ('from os import environ as ENV',)
LOG          = logging.getLogger('covenant.config')


class CovenantConfigurationError(Exception):
    pass


def import_file(filepath, config_dir = None, xvars = {}):
    if config_dir and not filepath.startswith(os.path.sep):
        filepath = os.path.join(config_dir, filepath)

    with open(filepath, 'r') as f:
        return load_yaml(Template(f.read(),
                         imports = _TPL_IMPORTS).render(**xvars))

def load_conf(xfile, options = None):
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    config_dir = os.path.dirname(os.path.abspath(xfile))

    with open(xfile, 'r') as f:
        conf = parse_conf(load_yaml(f))

    for name, module in MODULES.iteritems():
        LOG.info("module init: %r", name)
        module.init(conf)

    for x in ('module', 'plugin', 'filter'):
        path = conf['general'].get('%ss_path' % x)
        if path and os.path.isdir(path):
            DwhoLibLoader.load_dir(x, path)

    if not conf.get('endpoints'):
        raise CovenantConfigurationError("Missing 'endpoints' section in configuration")

    for name, ept_cfg in conf['endpoints'].iteritems():
        cfg     = {'general':  dict(conf['general']),
                   'covenant': {'endpoint_name': name,
                                'config_dir':    config_dir},
                   'vars' :    {}}
        metrics = []

        if 'plugin' not in ept_cfg:
            raise CovenantConfigurationError("Missing 'plugin' option in endpoint: %r" % name)

        if ept_cfg['plugin'] not in PLUGINS:
            raise CovenantConfigurationError("Invalid plugin %r in endpoint: %r"
                                             % (ept_cfg['plugin'],
                                                name))
        cfg['covenant']['plugin_name'] = ept_cfg['plugin']

        if ept_cfg.get('import_vars'):
            cfg['vars'].update(import_file(ept_cfg['import_vars'], config_dir, cfg))

        if 'vars' in ept_cfg:
            cfg['vars'].update(dict(ept_cfg['vars']))

        if ept_cfg.get('import_metrics'):
            metrics.extend(import_file(ept_cfg['import_metrics'], config_dir, cfg))

        if 'metrics' in ept_cfg:
            metrics.extend(list(ept_cfg['metrics']))

        if not metrics:
            raise CovenantConfigurationError("Missing 'metrics' option in endpoint: %r" % name)

        cfg['credentials'] = None
        if ept_cfg.get('credentials'):
            cfg['credentials'] = ept_cfg['credentials']

        cfg['metrics'] = metrics

        endpoint = PLUGINS[ept_cfg['plugin']](name)
        ENDPOINTS.register(endpoint)
        LOG.info("endpoint init: %r", name)
        endpoint.init(cfg)
        LOG.info("endpoint safe_init: %r", name)
        endpoint.safe_init()
        DWHO_THREADS.append(endpoint.at_stop)

    if not options or not isinstance(options, object):
        return conf

    for def_option in get_default_options().iterkeys():
        if getattr(options, def_option, None) is None \
           and def_option in conf['general']:
            setattr(options, def_option, conf['general'][def_option])

    setattr(options, 'configuration', conf)

    return options


def start_endpoints():
    for name, endpoint in ENDPOINTS.iteritems():
        if endpoint.enabled and endpoint.autostart:
            LOG.info("endpoint at_start: %r", name)
            endpoint.at_start()
