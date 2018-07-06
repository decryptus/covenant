# -*- coding: utf-8 -*-
"""covenant filters"""

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

from covenant.classes.exceptions import CovenantConfigurationError
from sonicprobe.helpers import linesubst

LOG        = logging.getLogger('covenant.plugins')


class CovenantFilters(dict):
    def register(self, xfilter):
        if not issubclass(xfilter, CovenantFilterBase):
            raise TypeError("Invalid Filter class. (class: %r)" % xfilter)
        return dict.__setitem__(self, xfilter.FILTER_NAME, xfilter)

FILTERS    = CovenantFilters()


class CovenantNoResult(object):
    pass

# TODO
class CovenantResultFailed(object):
    pass


class CovenantFilterBase(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def FILTER_NAME(self):
        return

    def __init__(self, **kwargs):
        self.__kwargs     = kwargs
        self.__value      = None
        self.__labelvalue = None
        self.init()

    @property
    def kwargs(self):
        return copy.copy(self._CovenantFilterBase__kwargs)

    @kwargs.setter
    def kwargs(self, kwargs):
        return self

    @property
    def value(self):
        return copy.copy(self._CovenantFilterBase__value)

    @value.setter
    def value(self, value):
        return self

    @property
    def labelvalue(self):
        return copy.copy(self._CovenantFilterBase__labelvalue)

    @labelvalue.setter
    def labelvalue(self, labelvalue):
        return self

    @abc.abstractmethod
    def init(self):
        return

    def __call__(self, value = None, labelvalue = None):
        self.__value      = value
        self.__labelvalue = labelvalue
        return self.run()

    @abc.abstractmethod
    def run(self):
        return

    def get_vars(self, xvars = None):
        if isinstance(xvars, dict) and self.labelvalue:
            xvars.update(self.labelvalue.vars())

        return xvars

    def build_args(self, args, xvars = None, step = 1):
        if step and self.labelvalue:
            if isinstance(xvars, dict):
                xvars.update(self.labelvalue.vars())
            else:
                xvars = self.labelvalue.vars()

        if not xvars:
            return args

        if isinstance(args, basestring):
            return linesubst(args, xvars)
        elif isinstance(args, (int, long, float)):
            return linesubst(str(args), xvars)
        elif isinstance(args, (list, tuple)):
            r = []
            for arg in args:
                r.append(self.build_args(arg, xvars, 0))
            return r
        elif isinstance(args, dict):
            r = {}
            for k, v in args.iteritems():
                r[k] = self.build_args(v, xvars, 0)
            return r

        return args
