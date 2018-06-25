# -*- coding: utf-8 -*-
"""covenant plugins"""

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

import abc
import copy
import logging
import Queue
import re
import threading
import uuid

from covenant.classes.filters import FILTERS
from dwho.classes.plugins import DWhoPluginBase
from dwho.config import load_credentials
from prometheus_client import (CollectorRegistry,
                               generate_latest as pc_generate_latest)
from prometheus_client import (Counter as prom_counter,
                               Gauge as prom_gauge,
                               Histogram as prom_histogram,
                               Summary as prom_summary)

LOG                   = logging.getLogger('covenant.plugins')

_DEFAULT_PROM_METHODS = {'prom_counter':   'inc',
                         'prom_gauge':     'set',
                         'prom_histogram': 'observe',
                         'prom_summary':   'observe'}


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


class CovenantEPTObject(object):
    def __init__(self, name, uid, endpoint, method, params, args, callback):
        self.name     = name
        self.uid      = uid
        self.endpoint = endpoint
        self.method   = method
        self.params   = params
        self.args     = args
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


class CovenantEPTSync(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, name):
        self.name       = name
        self.queue      = Queue.Queue()
        self.results    = {}

    def qput(self, item):
        return self.queue.put(item)

    def qget(self, block = True, timeout = None):
        return self.queue.get(block, timeout)


class CovenantLabelValue(object):
    def __init__(self, labelname, labelvalue = None, labeldefault = None):
        self.labelname    = labelname
        self.labelvalue   = labelvalue
        self.labeldefault = labeldefault
        self.metricvalue  = None

        if labelvalue is None:
            self.labelvalue = self.labeldefault
        elif isinstance(labelvalue, (list, tuple, set)):
            if len(labelvalue) > 0:
                self.labelvalue = list(labelvalue)[0]
            else:
                self.labelvalue = self.labeldefault
        elif isinstance(labelvalue, dict):
            if len(labelvalue) > 0:
                self.labelvalue = labelvalue.popitem()[1]
            else:
                self.labelvalue = self.labeldefault

    def set(self, metricvalue):
        self.metricvalue = metricvalue
        return self

    def get(self):
        return self.metricvalue

    def vars(self):
        return {'__labelname':    self.labelname,
                '__labelvalue':   self.labelvalue,
                '__labeldefault': self.labeldefault}


class CovenantLabels(object):
    def __init__(self, labelname, labelvalues = None, labeldefault = None, labelstatic = True, label_tasks = None, value_tasks = None):
        self.labelname    = labelname
        self.labelvalues  = []
        self.labeldefault = labeldefault
        self.labelstatic  = labelstatic
        self.label_tasks  = label_tasks
        self.value_tasks  = value_tasks

        if labelvalues is not None:
            if not isinstance(labelvalues, list):
                labelvalues = [labelvalues]

            for labelvalue in labelvalues:
                self.labelvalues.append(CovenantLabelValue(labelname,
                                                           labelvalue,
                                                           labeldefault))

    def task_label(self, data):
        if self.labelstatic:
            return

        self.labelvalues = []
        nvalues          = []
        values           = copy.copy(data)

        if not isinstance(values, list):
            values = [values]

        if not self.label_tasks:
            nvalues = values
        else:
            for value in values:
                for task in self.label_tasks:
                    value = task(value = value)
                nvalues.append(value)

        for value in nvalues:
            self.labelvalues.append(CovenantLabelValue(self.labelname,
                                                       value,
                                                       self.labeldefault))

        return self

    def task_value(self, data, value_tasks = None):
        tasks = value_tasks or self.value_tasks
        if not tasks:
            return self

        for labelvalue in self.labelvalues:
            value = copy.copy(data)
            for task in tasks:
                value = task(value = value, labelvalue = labelvalue)
            labelvalue.set(value)

        return self


class CovenantCollect(object):
    def __init__(self, metric, method = None, value = None, default = None, labels = None, value_tasks = None):
        self.metric      = metric
        self.method      = method
        self.value       = value
        self.default     = default
        self.labels      = labels
        self.value_tasks = value_tasks

    def __call__(self, data):
        if self.value is not None:
            data = self.value

        data = copy.copy(data)

        if self.labels:
            for label in self.labels:
                label.task_label(data)
                label.task_value(data, self.value_tasks)
        elif self.value_tasks:
            for task in self.value_tasks:
                data = task(value = data)

        if self.default is not None and data is None:
            data = self.default

        if not self.labels:
            try:
                getattr(self.metric, self.method)(data)
            except Exception, e:
                LOG.exception("metric: %r, data: %r, error: %r", self.metric._name, data, e)
                raise
            return

        for label in self.labels:
            for labelvalue in label.labelvalues:
                method = getattr(self.metric.labels(
                                    **{labelvalue.labelname: labelvalue.labelvalue}),
                                    self.method)

                try:
                    method(labelvalue.get())
                except Exception, e:
                    LOG.exception("metric: %r, data: %r, error: %r", self.metric._name, labelvalue.get(), e)
                    raise


class CovenantCtrlLoop(object):
    @classmethod
    def iter(cls, f = None):
        def g(*args, **kwargs):
            r     = []
            kargs = copy.copy(kwargs)

            if not hasattr(kwargs['value'], '__iter__'):
                if not f:
                    return copy.copy(kargs['value'])
                return f(*args, **kargs)

            for v in kwargs['value']:
                kargs['value'] = copy.copy(v)
                if not f:
                    r.append(kargs['value'])
                else:
                    r.append(f(*args, **kargs))

            return r
        return g

    @classmethod
    def dict(cls, f = None):
        def g(*args, **kwargs):
            r     = []
            kargs = copy.copy(kwargs)

            if not isinstance(kwargs['value'], dict):
                if not f:
                    return copy.copy(kwargs['value'])
                return f(*args, **kargs)

            for k, v in kwargs['value'].iteritems():
                kargs['key']   = k
                kargs['value'] = copy.copy(v)
                if not f:
                    r.append({'key': kargs['key'], 'value': kargs['value']})
                else:
                    r.append(f(*args, **kargs))

            return r
        return g

    @classmethod
    def dict_keys(cls, f = None):
        def g(*args, **kwargs):
            r     = []
            kargs = copy.copy(kwargs)

            if not hasattr(kwargs['value'], 'iterkeys'):
                if not f:
                    return kargs['value']
                return f(*args, **kargs)

            for k in kwargs['value'].iterkeys():
                kargs['value'] = k
                if not f:
                    r.append(kargs['value'])
                else:
                    r.append(f(*args, **kargs))

            return r
        return g

    @classmethod
    def dict_values(cls, f = None):
        def g(*args, **kwargs):
            r     = []
            kargs = copy.copy(kwargs)

            if not isinstance(kwargs['value'], dict):
                if not f:
                    return kargs['value']
                return f(*args, **kargs)

            for v in kwargs['value'].itervalues():
                kargs['value'] = copy.copy(v)
                if not f:
                    r.append(kargs['value'])
                else:
                    r.append(f(*args, **kargs))

            return r
        return g


class CovenantTarget(object):
    def __init__(self, name, config, collects, registry, credentials = None):
        self.name        = name or ''
        self.config      = dict(config)
        self.collects    = []
        self.registry    = registry
        self.labels      = []
        self.label_tasks = []
        self.value_tasks = []
        self.credentials = credentials

        if 'labels' in self.config:
            self.labels = self.load_labels(self.config['labels'])

        if 'label_tasks' in self.config:
            self.label_tasks = self.load_tasks(self.config['label_tasks'])

        if 'value_tasks' in self.config:
            self.value_tasks = self.load_tasks(self.config['value_tasks'])

        if 'credentials' in self.config:
            if self.config['credentials'] is None:
                self.credentials = None
            else:
                self.credentials = load_credentials(self.config['credentials'])

        self.load_collects(collects)

    @classmethod
    def _sanitize_task_args(cls, args):
        r = copy.copy(args)

        for argname in args.iterkeys():
            if isinstance(argname, basestring) \
               and argname.startswith('@'):
                del r[argname]

        return r

    @classmethod
    def load_tasks(cls, tasks):
        r = []

        for task in tasks:
            name, func = (None, None)
            taskargs   = cls._sanitize_task_args(task)

            if '@filter' in task:
                name = task.pop('@filter')
                if name not in FILTERS:
                    raise ValueError("unknown @filter: %r" % name)

                func = FILTERS[name](**taskargs)

            if '@loop' in task:
                name = task.pop('@loop')
                if name is True:
                    name = 'iter'
                if not hasattr(CovenantCtrlLoop, name):
                    raise ValueError("unknown @loop: %r" % name)

                if func:
                    func = getattr(CovenantCtrlLoop, name)(func)
                else:
                    func = getattr(CovenantCtrlLoop, name)(**taskargs)

            r.append(func)

        return r

    def load_labels(self, labels, label_tasks = [], value_tasks = []):
        labelnames = []
        clabels    = []

        for label in labels:
            name     = label['name']
            value    = None
            default  = label.get('default')
            static   = label.get('static')
            ltasks   = copy.copy(label_tasks)
            vtasks   = copy.copy(value_tasks)

            if 'label_tasks' in label:
                if label['label_tasks']:
                    ltasks = self.load_tasks(label['label_tasks'])
                    if static is None:
                        static = False
                else:
                    ltasks = []

            if 'value_tasks' in label and value is None:
                if label['value_tasks']:
                    vtasks = self.load_tasks(label['value_tasks'])
                else:
                    vtasks = []

            labelnames.append(name)
            clabels.append(CovenantLabels(
                               name,
                               value,
                               default,
                               bool(static),
                               ltasks,
                               vtasks))

        return (labelnames, clabels)

    def load_collects(self, collects):
        for c in collects:
            for key, value in c.iteritems():
                xtype = "prom_%s" % value['type'].lower()
                if xtype not in globals():
                    raise ValueError("unknown metric type: %r in %r" % (xtype, key))

                metric = globals()[xtype]
                method = _DEFAULT_PROM_METHODS[xtype]

                if 'method' in value:
                    method = value['method'].strip('_')

                if not hasattr(metric(("a%s" % uuid.uuid4()).replace('-', ':'),
                                      '',
                                      registry = CollectorRegistry()),
                               method):
                    raise ValueError("unknown method %r for %r in %r"
                                     % (method, value['type'], key))

                kwds    = {'name':          value.get('name') or key,
                           'documentation': value.pop('documentation'),
                           'registry':      self.registry}

                labels  = copy.copy(self.labels)
                clabels = []
                vtasks  = copy.copy(self.value_tasks)

                if 'labels' in value:
                    labels = []
                    if value['labels']:
                        labels = self.load_labels(value['labels'],
                                                  copy.copy(self.label_tasks),
                                                  copy.copy(self.value_tasks))

                if labels:
                    (kwds['labelnames'], clabels) = labels

                if 'value_tasks' in value:
                    vtasks = []
                    if value['value_tasks']:
                        vtasks = self.load_tasks(value['value_tasks'])

                self.collects.append(CovenantCollect(
                                        metric        = metric(**kwds),
                                        method        = method,
                                        value         = value.get('value'),
                                        default       = value.get('default'),
                                        labels        = clabels,
                                        value_tasks   = vtasks))

    def __call__(self, data):
        for collect in self.collects:
            collect(data)


class CovenantPlugBase(threading.Thread, DWhoPluginBase):
    __metaclass__ = abc.ABCMeta

    def __init__(self, name):
        threading.Thread.__init__(self)
        DWhoPluginBase.__init__(self)
        self.daemon      = True
        self.name        = name
        self.targets     = []
        self.registry    = CollectorRegistry()
        self.credentials = None

    def safe_init(self):
        if self.config.get('credentials'):
            self.credentials = load_credentials(self.config['credentials'],
                                                config_dir = self.config['covenant']['config_dir'])

        for target in self.config['metrics']:
            target['registry']    = self.registry
            target['credentials'] = self.credentials

            self.targets.append(CovenantTarget(**target))

        EPTS_SYNC.register(CovenantEPTSync(self.name))

    def at_start(self):
        if self.name in EPTS_SYNC:
            self.start()

    def generate_latest(self):
        return pc_generate_latest(self.registry)

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
            except Exception, e:
                obj.add_error(str(e))
                LOG.exception("%r", e)
            else:
                obj.set_result(r)
            finally:
                obj()

    def __call__(self):
        self.start()
        return self
