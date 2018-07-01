# -*- coding: utf-8 -*-
"""builtins filter"""

__author__  = "Adrien DELLE CAVE"
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

import logging

from covenant.classes.filters import CovenantFilterBase, FILTERS

LOG = logging.getLogger('covenant.filters.builtins')

_ALLOWED_FUNCTIONS = ('bool',
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
                raise ValueError("built-in function not allowed: %r", func)
            self._funcs.append(__builtins__[func])

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
