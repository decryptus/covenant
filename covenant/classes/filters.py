# -*- coding: utf-8 -*-
# Copyright (C) 2018-2019 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.classes.filters"""

import abc
import copy
import logging
import six

from sonicprobe.helpers import linesubst

LOG        = logging.getLogger('covenant.filters')


class CovenantFilters(dict):
    def register(self, xfilter):
        if not issubclass(xfilter, CovenantFilterBase):
            raise TypeError("Invalid Filter class. (class: %r)" % xfilter)
        return dict.__setitem__(self, xfilter.FILTER_NAME, xfilter)

FILTERS    = CovenantFilters()


class CovenantNoResult(object): # pylint: disable=useless-object-inheritance,too-few-public-methods
    pass

# TODO
class CovenantResultFailed(object): # pylint: disable=useless-object-inheritance,too-few-public-methods
    pass


class CovenantFilterBase(object): # pylint: disable=useless-object-inheritance
    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def FILTER_NAME(self): # pylint: disable=invalid-name
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
    def kwargs(self, kwargs): # pylint: disable=unused-argument
        return self

    @property
    def value(self):
        return copy.copy(self._CovenantFilterBase__value)

    @value.setter
    def value(self, value): # pylint: disable=unused-argument
        return self

    @property
    def labelvalue(self):
        return copy.copy(self._CovenantFilterBase__labelvalue)

    @labelvalue.setter
    def labelvalue(self, labelvalue): # pylint: disable=unused-argument
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

        if isinstance(args, six.string_types):
            return linesubst(args, xvars)

        if isinstance(args, (six.integer_types, float)):
            return linesubst(str(args), xvars)

        if isinstance(args, (list, tuple)):
            r = []
            for arg in args:
                r.append(self.build_args(arg, xvars, 0))
            return r

        if isinstance(args, dict):
            r = {}
            for k, v in six.iteritems(args):
                r[k] = self.build_args(v, xvars, 0)
            return r

        return args
