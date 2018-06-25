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

from covenant.classes.filters import CovenantFilterBase, FILTERS

LOG = logging.getLogger('covenant.filters.regex')


class CovenantRegexFilter(CovenantFilterBase):
    FILTER_NAME = 'regex'

    def init(self):
        func        = self.kwargs.get('func') or 'sub'
        self._fargs = self.kwargs

        if 'func' in self._fargs:
            del self._fargs['func']

        if 'pattern' in self._fargs:
            self._func = getattr(re.compile(self._fargs.pop('pattern')), func)
        else:
            self._func = getattr(re, func)

    def run(self):
        fargs           = self._fargs.copy()
        fargs['string'] = self.value

        return self._func(**fargs)


if __name__ != "__main__":
    def _start():
        FILTERS.register(CovenantRegexFilter)
    _start()
