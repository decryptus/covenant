# -*- coding: utf-8 -*-
"""builtintypes filter"""

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

LOG               = logging.getLogger('covenant.filters.builtintypes')

_BUILTIN_TYPES    = ('basestring',
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


def _builtin_types_funcs():
    funcs = set()
    for xtype in _BUILTIN_TYPES:
        for func in dir(__builtins__[xtype]):
            if not func.startswith('_'):
                funcs.add(func)

    return funcs

_BUILTIN_TYPES_FUNCS = _builtin_types_funcs()


class CovenantBuiltinTypesFilter(CovenantFilterBase):
    FILTER_NAME = 'builtintypes'

    def init(self):
        self._func = self.kwargs.pop('func')

        if self._func not in _BUILTIN_TYPES_FUNCS:
            raise ValueError("unable to found function: %r in builtin types" % self._func)

        self._args = list(self.kwargs.get('args', []) or [])

    def run(self):
        if self._func in _FUNCS_VALUE_ARG:
            return getattr(self._args[0], self._func)(self.value)

        return getattr(self.value, self._func)(*self._args)


if __name__ != "__main__":
    def _start():
        FILTERS.register(CovenantBuiltinTypesFilter)
    _start()
