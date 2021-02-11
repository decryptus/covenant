# -*- coding: utf-8 -*-
# Copyright (C) 2018-2021 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.classes.plugins"""

import abc
import copy
import logging
import threading

from six.moves import queue as _queue

from dwho.classes.plugins import DWhoPluginBase
from dwho.config import load_credentials
from prometheus_client import generate_latest

from covenant.classes.exceptions import CovenantTargetFailed # pylint: disable=unused-import
from covenant.classes.target import CovenantRegistry, CovenantTarget

LOG = logging.getLogger('covenant.plugins')


class CovenantPlugins(dict):
    def register(self, plugin):
        if not issubclass(plugin, CovenantPlugBase):
            raise TypeError("Invalid Plugin class. (class: %r)" % plugin)
        return dict.__setitem__(self, plugin.PLUGIN_NAME, plugin)

PLUGINS   = CovenantPlugins()


class CovenantEndpoints(dict):
    def register(self, endpoint):
        if not isinstance(endpoint, CovenantPlugBase):
            raise TypeError("Invalid Endpoint class. (class: %r)" % endpoint)
        return dict.__setitem__(self, endpoint.name, endpoint)

ENDPOINTS = CovenantEndpoints()


class CovenantEPTsSync(dict):
    def register(self, ept_sync):
        if not isinstance(ept_sync, CovenantEPTSync):
            raise TypeError("Invalid Endpoint Sync class. (class: %r)" % ept_sync)
        return dict.__setitem__(self, ept_sync.name, ept_sync)

EPTS_SYNC = CovenantEPTsSync()


class CovenantEPTObject(object): # pylint: disable=useless-object-inheritance
    def __init__(self, name, uid, endpoint, method, params, args, callback):
        self.name     = name
        self.uid      = uid
        self.endpoint = endpoint
        self.method   = method
        self.params   = params or {}
        self.args     = args or {}
        self.callback = callback
        self.result   = None
        self.errors   = []

    def get_uid(self):
        return self.uid

    def add_error(self, error):
        self.errors.append(error)
        return self

    def has_error(self):
        return len(self.errors) != 0

    def get_errors(self):
        return self.errors

    def set_result(self, result):
        self.result = result

        return self

    def get_result(self):
        return self.result

    def get_endpoint(self):
        return self.endpoint

    def get_method(self):
        return self.method

    def get_params(self):
        return self.params

    def get_args(self):
        return self.args

    def __call__(self):
        return self.callback(self)


class CovenantEPTSync(object): # pylint: disable=useless-object-inheritance
    __metaclass__ = abc.ABCMeta

    def __init__(self, name, xtype):
        self.name    = name
        self.type    = xtype
        self.queue   = _queue.Queue()
        self.results = {}

    def qput(self, item):
        return self.queue.put(item)

    def qget(self, block = True, timeout = None):
        return self.queue.get(block, timeout)


class CovenantPlugBase(threading.Thread, DWhoPluginBase):
    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def PLUGIN_NAME(self):
        return

    def __init__(self, name):
        threading.Thread.__init__(self)
        DWhoPluginBase.__init__(self)
        self.daemon      = True
        self.name        = name
        self.targets     = []
        self.registry    = CovenantRegistry()
        self.credentials = None
        self.type        = 'metric'

    def _load_targets(self, xtype):
        r = False

        if not self.config.get(xtype):
            return r

        for target in self.config[xtype]:
            if not isinstance(target.get('config'), dict):
                target['config'] = {}

            if not bool(target['config'].pop('enabled', True)):
                continue

            target['registry']    = self.registry
            target['credentials'] = self.credentials

            r = True
            self.targets.append(CovenantTarget(**target))

        return r

    def safe_init(self):
        if self.config.get('credentials'):
            self.credentials = load_credentials(self.config['credentials'],
                                                config_dir = self.config['covenant']['config_dir'])

        if self._load_targets('metrics'):
            self.type = 'metric'
            EPTS_SYNC.register(CovenantEPTSync(self.name, 'metric'))
        elif self._load_targets('probes'):
            self.type = 'probe'
            EPTS_SYNC.register(CovenantEPTSync(self.name, 'probe'))
        else:
            LOG.warning("no targets enabled for endpoint %r", self.name)

    def at_start(self):
        if self.name in EPTS_SYNC:
            self.start()

    def generate_latest(self, registry = None):
        if not registry:
            registry = self.registry

        return generate_latest(registry)

    def run(self):
        while True:
            r = None

            try:
                obj  = EPTS_SYNC[self.name].qget(True)
                func = "do_%s" % obj.get_method()
                if not hasattr(self, func):
                    LOG.warning("unknown method %r for endpoint %r", func, self.name)
                    continue

                r    = getattr(self, func)(obj)
            except Exception as e:
                obj.add_error(str(e))
                LOG.exception(e)
            else:
                obj.set_result(r)
            finally:
                obj()

    @abc.abstractmethod
    def _do_call(self, obj, targets = None, registry = None):
        pass

    def _fetch(self, obj):
        params = obj.get_params()
        if not params or not params.get('target'):
            return self._do_call(obj)

        registry = CovenantRegistry()

        targets = copy.deepcopy(self.targets)
        for target in targets:
            target.reload_collects(registry)

        return self._do_call(obj, targets, registry)

    def do_metrics(self, obj):
        return self._fetch(obj)

    def do_probes(self, obj):
        return self._fetch(obj)

    def __call__(self):
        self.start()
        return self
