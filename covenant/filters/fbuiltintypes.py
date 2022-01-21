# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.filters.fbuiltintypes"""

import logging
import six

from covenant.classes.filters import CovenantFilterBase, CovenantNoResult, FILTERS

if six.PY3:
    # pylint: disable=redefined-builtin,unused-import,ungrouped-imports
    from builtins import int as long
    from six import (string_types as basestring,
                     text_type as unicode)

LOG               = logging.getLogger('covenant.filters.builtintypes')

_BUILTIN_TYPES    = ('basestring',
                     'bytes',
                     'complex',
                     'dict',
                     'float',
                     'frozenset',
                     'int',
                     'list',
                     'long',
                     'None',
                     'set',
                     'slice',
                     'str',
                     'tuple',
                     'unicode')

_FUNCS_VALUE_ARG  = ('join',)
_FUNCS_LIST       = ('first', 'last', 'get')


def _builtin_types_funcs():
    funcs = set()
    for xtype in _BUILTIN_TYPES:
        if xtype in __builtins__:
            xfuncs = __builtins__[xtype]
        else:
            xfuncs = globals()[xtype]

        for func in dir(xfuncs):
            if not func.startswith('_'):
                funcs.add(func)

    return funcs

_BUILTIN_TYPES_FUNCS = _builtin_types_funcs()


class CovenantBuiltinTypesFilter(CovenantFilterBase):
    FILTER_NAME = 'builtintypes'

    def init(self):
        self._func = self.kwargs.pop('func')

        if self._func not in _BUILTIN_TYPES_FUNCS:
            raise ValueError("unable to find function: %r in builtin types" % self._func)

        self._args = list(self.kwargs.get('args', []) or [])

    def run(self):
        fargs = self.build_args(list(self._args))

        if isinstance(self.value, (list, tuple)) \
           and self._func in _FUNCS_LIST:
            func = self._func
            xlen = len(fargs)
            if xlen == 0:
                func = 'first'

            if not self.value:
                return CovenantNoResult()

            if func == 'first':
                return self.value[0]

            if func == 'last':
                return self.value[-1]

            if func == 'get':
                if xlen == 1:
                    return self.value[fargs[0]]
                return self.value[fargs[0]:fargs[1]]

        if self._func in _FUNCS_VALUE_ARG:
            return getattr(fargs[0], self._func)(self.value)

        return getattr(self.value, self._func)(*fargs)


if __name__ != "__main__":
    def _start():
        FILTERS.register(CovenantBuiltinTypesFilter)
    _start()
