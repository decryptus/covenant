# -*- coding: utf-8 -*-
"""regex filter"""

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
import re

from covenant.classes.filters import CovenantFilterBase, CovenantNoResult, FILTERS

LOG = logging.getLogger('covenant.filters.regex')

_MATCH_OBJECT_FUNCS = ('match', 'search')


class CovenantRegexFilter(CovenantFilterBase):
    FILTER_NAME = 'regex'

    @classmethod
    def _parse_flags(cls, flags):
        if isinstance(flags, int):
            return flags
        elif isinstance(flags, list):
            r = 0
            for x in flags:
                r |= cls._parse_flags(x)
            return r
        elif isinstance(flags, basestring):
            if flags.isdigit():
                return int(flags)
            return getattr(re, flags)

        return 0

    def init(self):
        func          = self.kwargs.get('func') or 'sub'

        self._fargs   = self.kwargs
        self._rfunc   = self.kwargs.get('return')
        self._rargs   = self.kwargs.get('return_args')
        _is_match_obj = func in _MATCH_OBJECT_FUNCS

        if _is_match_obj and not self._rfunc:
            self._rfunc = 'group'
            self._rargs = [1]

        if _is_match_obj and not self._rargs:
            self._rargs = [1]

        if 'func' in self._fargs:
            del self._fargs['func']

        if 'return' in self._fargs:
            del self._fargs['return']

        if 'return_args' in self._fargs:
            del self._fargs['return_args']

        if 'pattern' in self._fargs:
            flags = 0
            if 'flags' in self._fargs:
                flags = self._parse_flags(self._fargs.pop('flags'))

            self._func = getattr(re.compile(pattern = self._fargs.pop('pattern'),
                                            flags = flags),
                                 func)
        else:
            self._func = getattr(re, func)

    def run(self):
        fargs           = self._fargs.copy()
        fargs['string'] = self.value
        ret             = self._func(**fargs)
        if ret is None:
            return CovenantNoResult()

        if not self._rfunc:
            return ret

        if self._rargs:
            return getattr(ret, self._rfunc)(*self._rargs)

        return getattr(ret, self._rfunc)()


if __name__ != "__main__":
    def _start():
        FILTERS.register(CovenantRegexFilter)
    _start()
