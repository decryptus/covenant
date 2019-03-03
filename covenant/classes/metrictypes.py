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

from prometheus_client.metrics import (Counter,
                                       Enum,
                                       Gauge,
                                       Histogram,
                                       Info,
                                       Summary)

_DEFAULT_METRIC_TYPES         = {'counter':   {'obj':  Counter,
                                               'func': 'inc'},
                                 'enum':      {'obj':  Enum,
                                               'func': 'state'},
                                 'gauge':     {'obj':  Gauge,
                                               'func': 'set'},
                                 'histogram': {'obj':  Histogram,
                                               'func': 'observe'},
                                 'info':      {'obj':  Info,
                                               'func': 'info'},
                                 'summary':   {'obj':  Summary,
                                               'func': 'observe'}}

_DEFAULT_METRIC_TYPES_OBJECTS = tuple([x['obj'] for x in _DEFAULT_METRIC_TYPES.itervalues()])

LOG                           = logging.getLogger('covenant.metrictypes')


class CovenantMetricTypes(dict):
    def register(self, metric_type):
        if metric_type in _DEFAULT_METRIC_TYPES_OBJECTS:
            if self.__contains__(metric_type._type):
                raise KeyError("Metric type already exists: %r" % metric_type)
            return self.__setitem__(metric_type._type, metric_type)

        if not issubclass(metric_type, CovenantMetricBase):
            raise TypeError("Invalid Metric Type class: %r" % metric_type)
        elif self.__contains__(metric_type.NAME):
            raise KeyError("Metric type already exists: %r" % metric_type)

        return self.__setitem__(metric_type.NAME, metric_type)


METRICTYPES = CovenantMetricTypes()


def is_default_metric_type(name):
    return name in _DEFAULT_METRIC_TYPES

def get_default_metric_type_func(name):
    return _DEFAULT_METRIC_TYPES[name]['func']

def get_metric_type_default_func(name):
    if is_default_metric_type(name):
        return get_default_metric_type_func(name)
    return METRICTYPES[name].METHOD


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


class CovenantMetricTypeConstCounter(CovenantMetricTypeConstBase, Counter):
    NAME   = 'const_counter'
    METHOD = 'const'

    def const(self, value):
        self._value.set(float(value))


class CovenantMetricTypeConstGauge(CovenantMetricTypeConstBase, Gauge):
    NAME   = 'const_gauge'
    METHOD = 'const'

    def const(self, value):
        self._value.set(float(value))


class CovenantMetricTypeConstHistogram(CovenantMetricTypeConstBase, Histogram):
    NAME   = 'const_histogram'
    METHOD = 'const'

    def const(self, value):
        self._sum.set(value)
        for i, bound in enumerate(self._upper_bounds):
            if value <= bound:
                self._buckets[i].set(1)
                break


class CovenantMetricTypeConstSummary(CovenantMetricTypeConstBase, Summary):
    NAME   = 'const_summary'
    METHOD = 'const'

    def const(self, value):
        self._count.set(1)
        self._sum.set(value)


if __name__ != "__main__":
    def _start():
        for default_metric_type in _DEFAULT_METRIC_TYPES_OBJECTS:
            METRICTYPES.register(default_metric_type)
        METRICTYPES.register(CovenantMetricTypeConstCounter)
        METRICTYPES.register(CovenantMetricTypeConstGauge)
        METRICTYPES.register(CovenantMetricTypeConstHistogram)
        METRICTYPES.register(CovenantMetricTypeConstSummary)

    _start()
