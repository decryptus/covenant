# -*- coding: utf-8 -*-
"""covenant metrictypes"""

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
import logging

from prometheus_client import (CollectorRegistry,
                               Counter,
                               Gauge,
                               Histogram,
                               Summary)
from prometheus_client.core import (_floatToGoString,
                                    _INF,
                                    _MetricWrapper,
                                    _ValueClass)

_DEFAULT_METRIC_TYPES         = {'counter':   {'obj':  Counter,
                                               'func': 'inc'},
                                 'gauge':     {'obj':  Gauge,
                                               'func': 'set'},
                                 'histogram': {'obj':  Histogram,
                                               'func': 'observe'},
                                 'summary':   {'obj':  Summary,
                                               'func': 'observe'}}

_DEFAULT_METRIC_TYPES_OBJECTS = tuple([x['obj'] for x in _DEFAULT_METRIC_TYPES.itervalues()])

LOG                           = logging.getLogger('covenant.metrictypes')


class CovenantMetricTypes(dict):
    def register(self, metric_type):
        if metric_type in _DEFAULT_METRIC_TYPES_OBJECTS:
            if self.__contains__(metric_type.__wrapped__._type):
                raise KeyError("Metric type already exists: %r" % metric_type)
            return self.__setitem__(metric_type.__wrapped__._type, metric_type)

        if not hasattr(metric_type, '__wrapped__'):
            raise TypeError("Invalid Metric Type without attribute __wrapped__: %r" % metric_type)
        if not issubclass(metric_type.__wrapped__, CovenantMetricBase):
            raise TypeError("Invalid Metric Type class: %r" % metric_type)
        elif self.__contains__(metric_type.__wrapped__.NAME):
            raise KeyError("Metric type already exists: %r" % metric_type)

        return self.__setitem__(metric_type.__wrapped__.NAME, metric_type)


METRICTYPES = CovenantMetricTypes()


def is_default_metric_type(name):
    return name in _DEFAULT_METRIC_TYPES

def get_default_metric_type_func(name):
    return _DEFAULT_METRIC_TYPES[name]['func']

def get_metric_type_default_func(name):
    if is_default_metric_type(name):
        return get_default_metric_type_func(name)
    return METRICTYPES[name].__wrapped__.METHOD


class CovenantMetricBase(object):
    pass


class CovenantMetricTypeConstBase(CovenantMetricBase):
    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def NAME(self):
        return

    @abc.abstractproperty
    def METHOD(self):
        return

    def const(self, value):
        self._value.set(float(value))

    def _samples(self):
        return (('', {}, self._value.get()), )


@_MetricWrapper
class CovenantMetricTypeConstCounter(CovenantMetricTypeConstBase):
    NAME         = 'const_counter'
    METHOD       = 'const'

    _type        = 'counter'
    _reserved_labelnames = []

    def __init__(self, name, labelnames, labelvalues):
        self._value = _ValueClass(self._type, name, name, labelnames, labelvalues)


@_MetricWrapper
class CovenantMetricTypeConstGauge(CovenantMetricTypeConstBase):
    NAME         = 'const_gauge'
    METHOD       = 'const'

    _setted      = False
    _type        = 'gauge'
    _reserved_labelnames = []
    _MULTIPROC_MODES = frozenset(('min', 'max', 'livesum', 'liveall', 'all'))

    def __init__(self, name, labelnames, labelvalues, multiprocess_mode='all'):
        if (_ValueClass._multiprocess and
                multiprocess_mode not in self._MULTIPROC_MODES):
            raise ValueError('Invalid multiprocess mode: ' + multiprocess_mode)
        self._value = _ValueClass(
            self._type, name, name, labelnames, labelvalues,
            multiprocess_mode=multiprocess_mode)


@_MetricWrapper
class CovenantMetricTypeConstHistogram(CovenantMetricTypeConstBase):
    NAME         = 'const_histogram'
    METHOD       = 'const'

    _setted      = False
    _type        = 'histogram'
    _reserved_labelnames = ['histogram']

    def __init__(self, name, labelnames, labelvalues, buckets=(.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0, _INF)):
        self._sum = _ValueClass(self._type, name, name + '_sum', labelnames, labelvalues)
        buckets = [float(b) for b in buckets]
        if buckets != sorted(buckets):
            # This is probably an error on the part of the user,
            # so raise rather than sorting for them.
            raise ValueError('Buckets not in sorted order')
        if buckets and buckets[-1] != _INF:
            buckets.append(_INF)
        if len(buckets) < 2:
            raise ValueError('Must have at least two buckets')
        self._upper_bounds = buckets
        self._buckets = []
        bucket_labelnames = labelnames + ('le',)
        for b in buckets:
            self._buckets.append(_ValueClass(self._type, name, name + '_bucket', bucket_labelnames, labelvalues + (_floatToGoString(b),)))

    def const(self, amount):
        self._sum.set(amount)
        for i, bound in enumerate(self._upper_bounds):
            if amount <= bound:
                self._buckets[i].set(1)
                break

    def _samples(self):
        samples = []
        acc = 0
        for i, bound in enumerate(self._upper_bounds):
            acc += self._buckets[i].get()
            samples.append(('_bucket', {'le': _floatToGoString(bound)}, acc))
        samples.append(('_count', {}, acc))
        samples.append(('_sum', {}, self._sum.get()))
        return tuple(samples)


@_MetricWrapper
class CovenantMetricTypeConstSummary(CovenantMetricTypeConstBase):
    NAME       = 'const_summary'
    METHOD     = 'const'

    _setted    = False
    _type      = 'summary'
    _reserved_labelnames = ['quantile']

    def __init__(self, name, labelnames, labelvalues):
        self._count = _ValueClass(self._type, name, name + '_count', labelnames, labelvalues)
        self._sum = _ValueClass(self._type, name, name + '_sum', labelnames, labelvalues)

    def const(self, amount):
        self._count.set(1)
        self._sum.set(amount)

    def _samples(self):
        return (
            ('_count', {}, self._count.get()),
            ('_sum', {}, self._sum.get()))


if __name__ != "__main__":
    def _start():
        for default_metric_type in _DEFAULT_METRIC_TYPES_OBJECTS:
            METRICTYPES.register(default_metric_type)
        METRICTYPES.register(CovenantMetricTypeConstCounter)
        METRICTYPES.register(CovenantMetricTypeConstGauge)
        METRICTYPES.register(CovenantMetricTypeConstHistogram)
        METRICTYPES.register(CovenantMetricTypeConstSummary)

    _start()
