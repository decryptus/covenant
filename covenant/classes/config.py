# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.classes.config"""

import copy
import logging
import os
import signal
import six

from dwho.config import import_conf_files, init_modules, parse_conf, stop, DWHO_THREADS
from dwho.classes.libloader import DwhoLibLoader
from httpdis.httpdis import get_default_options
from mako.template import Template
from sonicprobe.helpers import load_yaml

from covenant.classes.exceptions import CovenantConfigurationError
from covenant.classes.plugins import ENDPOINTS, PLUGINS

_TPL_IMPORTS = ('from os import environ as ENV',
                'from sonicprobe.helpers import to_yaml as my')
LOG          = logging.getLogger('covenant.config')


def import_file(filepath, config_dir = None, xvars = None):
    if not xvars:
        xvars = {}

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

    conf = import_conf_files('modules', conf)

    init_modules(conf)

    for x in ('module', 'plugin', 'filter'):
        path = conf['general'].get('%ss_path' % x)
        if path and os.path.isdir(path):
            DwhoLibLoader.load_dir(x, path)

    if not conf.get('endpoints'):
        raise CovenantConfigurationError("Missing 'endpoints' section in configuration")

    for name, ept_cfg in six.iteritems(conf['endpoints']):
        cfg     = {'general':  copy.copy(conf['general']),
                   'covenant': {'endpoint_name': name,
                                'config_dir':    config_dir},
                   'vars' :    {}}
        metrics = []
        probes = []

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
            cfg['vars'].update(copy.deepcopy(ept_cfg['vars']))

        if ept_cfg.get('import_metrics'):
            metrics.extend(import_file(ept_cfg['import_metrics'], config_dir, cfg))

        if 'metrics' in ept_cfg:
            metrics.extend(copy.deepcopy(ept_cfg['metrics']))

        if ept_cfg.get('import_probes'):
            probes.extend(import_file(ept_cfg['import_probes'], config_dir, cfg))

        if 'probes' in ept_cfg:
            probes.extend(copy.deepcopy(ept_cfg['probes']))

        if not metrics and not probes:
            raise CovenantConfigurationError("Missing 'metrics' or 'probes' option in endpoint: %r" % name)

        if metrics and probes:
            raise CovenantConfigurationError("'metrics' and 'probes' aren't allowed in a same endpoint: %r" % name)

        cfg['credentials'] = None
        if ept_cfg.get('credentials'):
            cfg['credentials'] = ept_cfg['credentials']

        cfg['metrics'] = metrics
        cfg['probes'] = probes

        endpoint = PLUGINS[ept_cfg['plugin']](name)
        ENDPOINTS.register(endpoint)
        LOG.info("endpoint init: %r", name)
        endpoint.init(cfg)
        LOG.info("endpoint safe_init: %r", name)
        endpoint.safe_init()
        DWHO_THREADS.append(endpoint.at_stop)

    if not options or not isinstance(options, object):
        return conf

    for def_option in six.iterkeys(get_default_options()):
        if getattr(options, def_option, None) is None \
           and def_option in conf['general']:
            setattr(options, def_option, conf['general'][def_option])

    setattr(options, 'configuration', conf)

    return options


def start_endpoints():
    for name, endpoint in six.iteritems(ENDPOINTS):
        if endpoint.enabled and endpoint.autostart:
            LOG.info("endpoint at_start: %r", name)
            endpoint.at_start()
