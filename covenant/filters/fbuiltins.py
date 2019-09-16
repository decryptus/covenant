# -*- coding: utf-8 -*-
# Copyright (C) 2018-2019 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.filters.fbuiltins"""

import logging
import six

from covenant.classes.filters import CovenantFilterBase, FILTERS

if six.PY3:
    # pylint: disable=redefined-builtin,unused-import,ungrouped-imports
    from builtins import int as long
    from six import text_type as unicode
    from six.moves import range as xrange


LOG = logging.getLogger('covenant.filters.builtins')

_ALLOWED_FUNCTIONS = ('bin',
                      'bool',
                      'bytes',
                      'chr',
                      'cmp',
                      'complex',
                      'divmod',
                      'enumerate',
                      'dict',
                      'float',
                      'format',
                      'hex',
                      'id',
                      'int',
                      'len',
                      'long',
                      'max',
                      'min',
                      'oct',
                      'ord',
                      'pow',
                      'range',
                      'repr',
                      'reversed',
                      'round',
                      'set',
                      'slice',
                      'sorted',
                      'str',
                      'sum',
                      'tuple',
                      'type',
                      'unicode',
                      'unichr',
                      'xrange',
                      'zip')


class CovenantBuiltinsFilter(CovenantFilterBase):
    FILTER_NAME = 'builtins'

    def init(self):
        funcs       = self.kwargs.pop('func')
        self._funcs = []

        if not isinstance(funcs, list):
            funcs = [funcs]

        for func in funcs:
            if func not in _ALLOWED_FUNCTIONS:
                raise ValueError("built-in function not allowed: %r" % func)

            if func in __builtins__:
                self._funcs.append(__builtins__[func])
            else:
                self._funcs.append(globals()[func])

        self._fargs         = list(self.kwargs.get('args', []) or [])
        self._value_arg_pos = int(self.kwargs.get('value_arg_pos') or 0)

    def run(self):
        fargs = list(self._fargs)
        fargs.insert(self._value_arg_pos, self.value)
        fargs = self.build_args(fargs)

        for func in self._funcs:
            fargs = [func(*fargs)]

        return fargs.pop(0)


if __name__ != "__main__":
    def _start():
        FILTERS.register(CovenantBuiltinsFilter)
    _start()
