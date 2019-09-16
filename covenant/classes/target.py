# -*- coding: utf-8 -*-
# Copyright (C) 2018-2019 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.classes.target"""

import copy
import logging
import uuid
import six

from dwho.config import load_credentials
from prometheus_client import CollectorRegistry

from covenant.classes.collect import CovenantCollect
from covenant.classes.controls import CovenantCtrlLabelize, CovenantCtrlLoop
from covenant.classes.filters import FILTERS
from covenant.classes.label import CovenantLabels
from covenant.classes.metrictypes import (get_metric_type_default_func,
                                          get_metric_type_default_validator,
                                          METRICTYPES)

LOG                   = logging.getLogger('covenant.target')


class CovenantRegistry(CollectorRegistry):
    def collect(self):
        '''Yields metrics from the collectors in the registry.'''
        collectors = None
        with self._lock:
            collectors = copy.copy(self._collector_to_names)
        for collector in collectors:
            if hasattr(collector, '_removed') and collector._removed: # pylint: disable=protected-access
                continue
            for metric in collector.collect():
                yield metric


class CovenantTarget(object): # pylint: disable=useless-object-inheritance
    def __init__(self,
                 name,
                 config,
                 collects,
                 registry,
                 labels        = None,
                 label_tasks   = None,
                 value_tasks   = None,
                 on_fail       = None,
                 on_noresult   = None,
                 metric_prefix = None,
                 credentials   = None):
        self.name          = name or ''
        self.__config      = copy.copy(config)
        self.collects      = []
        self.registry      = registry
        self.labels        = []
        self.label_tasks   = []
        self.value_tasks   = []
        self.metric_prefix = metric_prefix
        self.__credentials = copy.copy(credentials)

        if labels:
            self.labels = self.load_labels(labels)

        if label_tasks:
            self.label_tasks = self.load_tasks(label_tasks, 'label')

        if value_tasks:
            self.value_tasks = self.load_tasks(value_tasks)

        self.on_fail     = on_fail
        self.on_noresult = on_noresult

        if 'credentials' in self.config:
            if self.__config['credentials'] is None:
                self.__credentials = None
            else:
                self.__credentials = load_credentials(self.config['credentials'])
            del self.__config['credentials']

        self.load_collects(collects)

    @property
    def config(self):
        return copy.copy(self._CovenantTarget__config) # pylint: disable=no-member

    @config.setter
    def config(self, config): # pylint: disable=unused-argument
        return self

    @property
    def credentials(self):
        return copy.copy(self._CovenantTarget__credentials) # pylint: disable=no-member

    @credentials.setter
    def credentials(self, credentials): # pylint: disable=unused-argument
        return self

    @classmethod
    def _config_on(cls, option, config, default):
        if option not in config:
            return default

        r = None
        if config[option]:
            r = config[option]

        return r

    @classmethod
    def _sanitize_task_args(cls, args):
        r = copy.copy(args)

        for argname in six.iterkeys(args):
            if isinstance(argname, six.string_types) \
               and argname.startswith('@'):
                del r[argname]

        return r

    @classmethod
    def load_tasks(cls, tasks, xtype = 'value'):
        r = []

        for task in tasks:
            name, func = (None, None)
            taskargs   = cls._sanitize_task_args(task)

            if xtype == 'label' and '@labelize' in task:
                name = task.pop('@labelize')
                if name is True:
                    name = 'dict'
                if not hasattr(CovenantCtrlLabelize, name) or name.startswith('_'):
                    raise ValueError("unknown @labelize: %r" % name)

                r.append(getattr(CovenantCtrlLabelize, name)(**taskargs))
                continue

            if '@filter' in task:
                name = task.pop('@filter')
                if name not in FILTERS:
                    raise ValueError("unknown @filter: %r" % name)

                func = FILTERS[name](**taskargs)

            if '@loop' in task:
                name = task.pop('@loop')
                if name is True:
                    name = 'iter'
                if not hasattr(CovenantCtrlLoop, name) or name.startswith('_'):
                    raise ValueError("unknown @loop: %r" % name)

                if func:
                    func = getattr(CovenantCtrlLoop, name)(func)
                else:
                    func = getattr(CovenantCtrlLoop, name)(**taskargs)

            if func:
                r.append(func)

        return r

    def load_labels(self, labels, label_tasks = None, value_tasks = None, on_fail = None, on_noresult = None):
        if not label_tasks:
            label_tasks = []

        if not value_tasks:
            value_tasks = []

        labelnames = set()
        clabels    = []

        for label in labels:
            name        = label['name']
            static      = label.get('static')
            ltasks      = copy.copy(label_tasks)
            vtasks      = copy.copy(value_tasks)
            on_fail     = copy.copy(on_fail)
            on_noresult = copy.copy(on_noresult)

            if 'label_tasks' in label:
                ltasks = []
                if label['label_tasks']:
                    ltasks = self.load_tasks(label['label_tasks'], 'label')
                    if static is None:
                        static = False

            if 'value_tasks' in label:
                vtasks = []
                if label['value_tasks']:
                    vtasks = self.load_tasks(label['value_tasks'])

            on_fail     = self._config_on('on_fail', label, on_fail)
            on_noresult = self._config_on('on_noresult', label, on_noresult)

            labelnames.add(name)
            clabels.append(CovenantLabels(
                name,
                label.get('value'),
                label.get('default'),
                bool(static),
                ltasks,
                vtasks,
                on_fail,
                on_noresult))

        return (labelnames, clabels)

    def load_collects(self, collects):
        for c in collects:
            for key, value in six.iteritems(c):
                xtype = value['type'].lower()
                if xtype not in METRICTYPES:
                    raise ValueError("unknown metric type: %r in %r" % (xtype, key))

                metric    = METRICTYPES[xtype]
                method    = get_metric_type_default_func(xtype)
                validator = get_metric_type_default_validator(xtype)
                name      = value.get('name') or key

                if 'metric_prefix' in value:
                    if value['metric_prefix']:
                        name = "%s_%s" % (value['metric_prefix'], name)
                elif self.metric_prefix:
                    name = "%s_%s" % (self.metric_prefix, name)

                if 'method' in value:
                    method = value['method'].strip('_')

                if not hasattr(metric(("a%s" % uuid.uuid4()).replace('-', ':'),
                                      '',
                                      registry = CovenantRegistry()),
                               method):
                    raise ValueError("unknown method %r for %r in %r"
                                     % (method, value['type'], key))

                kwds        = {'name':          name,
                               'documentation': value.pop('documentation'),
                               'registry':      self.registry}

                labels      = copy.copy(self.labels)
                clabels     = []
                vtasks      = copy.copy(self.value_tasks)
                on_fail     = copy.copy(self.on_fail)
                on_noresult = copy.copy(self.on_noresult)

                if 'labels' in value:
                    labels = []
                    if value['labels']:
                        labels = self.load_labels(value['labels'],
                                                  copy.copy(self.label_tasks),
                                                  copy.copy(self.value_tasks),
                                                  copy.copy(self.on_fail),
                                                  copy.copy(self.on_noresult))

                if labels:
                    (kwds['labelnames'], clabels) = labels

                if 'value_tasks' in value:
                    vtasks = []
                    if value['value_tasks']:
                        vtasks = self.load_tasks(value['value_tasks'])

                on_fail     = self._config_on('on_fail', value, on_fail)
                on_noresult = self._config_on('on_noresult', value, on_noresult)

                self.collects.append(CovenantCollect(
                    name        = value.get('name') or key,
                    metric      = metric(**kwds),
                    method      = method,
                    validator   = validator,
                    value       = value.get('value'),
                    default     = value.get('default'),
                    labels      = clabels,
                    value_tasks = vtasks,
                    on_fail     = on_fail,
                    on_noresult = on_noresult))

    def __call__(self, data):
        for collect in self.collects:
            collect(data)
