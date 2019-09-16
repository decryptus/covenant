# -*- coding: utf-8 -*-
# Copyright (C) 2018-2019 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.classes.controls"""

import copy
import logging
import re
import six

from covenant.classes.label import CovenantLabelValuesCollection, CovenantLabelValue, CovenantNoResult

LOG = logging.getLogger('covenant.controls')


class CovenantCtrlLabelize(object): # pylint: disable=useless-object-inheritance
    @staticmethod
    def _to_remove(key, kargs):
        r = False

        if 'include' in kargs:
            r = key not in kargs['include']

        if 'exclude' in kargs and key in kargs['exclude']:
            r = key in kargs['exclude']

        if 'include_regex' in kargs:
            r = not re.match(kargs['include_regex'], key)

        if 'exclude_regex' in kargs:
            r = bool(re.match(kargs['exclude_regex'], key))

        return r

    @classmethod
    def dict(cls, *largs, **lkargs): # pylint: disable=unused-argument
        def func(*args, **kwargs): # pylint: disable=unused-argument
            r     = CovenantLabelValuesCollection()
            kargs = copy.copy(kwargs)

            if not isinstance(kwargs['value'], dict):
                return kwargs['value']

            if 'key' in lkargs and 'value' in lkargs:
                metricvalue = kwargs['value'].get(lkargs['value'])
                if metricvalue is None:
                    metricvalue = lkargs.get('default')
                kargs['value'] = CovenantLabelValue(labelvalue  = kwargs['value'][lkargs['key']],
                                                    metricvalue = metricvalue,
                                                    remove      = cls._to_remove(kwargs['value'][lkargs['key']], lkargs))
                return kargs['value']

            xlen = len(kwargs['value'])

            for k, v in six.iteritems(kwargs['value']):
                metricvalue = v
                if 'value' in lkargs:
                    metricvalue = v.get(lkargs['value'])
                    if metricvalue is None:
                        metricvalue = lkargs.get('default')
                kargs['value'] = CovenantLabelValue(labelvalue  = k,
                                                    metricvalue = metricvalue,
                                                    remove      = cls._to_remove(k, lkargs))

                if xlen == 1:
                    return kargs['value']

                r.append(kargs['value'])

            if not r and not lkargs.get('empty'):
                return CovenantNoResult()

            return r
        return func


class CovenantCtrlLoop(object): # pylint: disable=useless-object-inheritance
    @classmethod
    def iter(cls, f = None):
        def func(*args, **kwargs):
            r     = []
            kargs = copy.copy(kwargs)

            if not hasattr(kwargs['value'], '__iter__'):
                if not f:
                    return kargs['value']
                return f(*args, **kargs)

            for v in kwargs['value']:
                kargs['value'] = copy.copy(v)
                if not f:
                    r.append(kargs['value'])
                else:
                    r.append(f(*args, **kargs))

            return r
        return func

    @classmethod
    def dict(cls, f = None):
        def func(*args, **kwargs):
            r     = []
            kargs = copy.copy(kwargs)

            if not isinstance(kwargs['value'], dict):
                if not f:
                    return kwargs['value']
                return f(*args, **kargs)

            for k, v in six.iteritems(kwargs['value']):
                kargs['key']   = k
                kargs['value'] = copy.copy(v)
                if not f:
                    r.append({'key': kargs['key'], 'value': kargs['value']})
                else:
                    r.append(f(*args, **kargs))

            return r
        return func

    @classmethod
    def dict_keys(cls, f = None):
        def func(*args, **kwargs):
            r     = []
            kargs = copy.copy(kwargs)

            if not hasattr(kwargs['value'], 'keys'):
                if not f:
                    return kargs['value']
                return f(*args, **kargs)

            for k in six.iterkeys(kwargs['value']):
                kargs['value'] = k
                if not f:
                    r.append(kargs['value'])
                else:
                    r.append(f(*args, **kargs))

            return r
        return func

    @classmethod
    def dict_values(cls, f = None):
        def func(*args, **kwargs):
            r     = []
            kargs = copy.copy(kwargs)

            if not isinstance(kwargs['value'], dict):
                if not f:
                    return kargs['value']
                return f(*args, **kargs)

            for v in six.itervalues(kwargs['value']):
                kargs['value'] = copy.copy(v)
                if not f:
                    r.append(kargs['value'])
                else:
                    r.append(f(*args, **kargs))

            return r
        return func
