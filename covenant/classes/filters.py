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

LOG        = logging.getLogger('covenant.plugins')


class CovenantFilters(dict):
    def register(self, xfilter):
        if not issubclass(xfilter, CovenantFilterBase):
            raise TypeError("Invalid Filter class. (class: %r)" % xfilter)
        return dict.__setitem__(self, xfilter.FILTER_NAME, xfilter)

FILTERS    = CovenantFilters()


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
