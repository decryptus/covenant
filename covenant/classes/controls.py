# -*- coding: utf-8 -*-
"""covenant controls"""

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

import copy
import logging
import re

from covenant.classes.label import CovenantLabelValuesCollection, CovenantLabelValue

LOG = logging.getLogger('covenant.controls')


class CovenantCtrlLabelize(object):
    @staticmethod
    def _to_remove(key, kargs):
        r = False

        if 'include' in kargs:
            r = key not in lkargs['include']

        if 'exclude' in kargs and key in kargs['exclude']:
            r = key in kargs['exclude']

        if 'include_regex' in kargs:
            r = not re.match(kargs['include_regex'], key)

        if 'exclude_regex' in kargs:
            r = bool(re.match(kargs['exclude_regex'], key))

        return r

    @classmethod
    def dict(cls, *largs, **lkargs):
        def g(*args, **kwargs):
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

            for k, v in kwargs['value'].iteritems():
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
                else:
                    r.append(kargs['value'])

            return r
        return g


class CovenantCtrlLoop(object):
    @classmethod
    def iter(cls, f = None):
        def g(*args, **kwargs):
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
        return g

    @classmethod
    def dict(cls, f = None):
        def g(*args, **kwargs):
            r     = []
            kargs = copy.copy(kwargs)

            if not isinstance(kwargs['value'], dict):
                if not f:
                    return kwargs['value']
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
