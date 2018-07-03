# -*- coding: utf-8 -*-
"""jmespath filter"""

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
import jmespath

from covenant.classes.filters import CovenantFilterBase, FILTERS

LOG = logging.getLogger('covenant.filters.jmespath')


class CovenantJMESPathFilter(CovenantFilterBase):
    FILTER_NAME = 'jmespath'

    def init(self):
        self._fargs   = self.kwargs
        self._compile = None

        if '{{' not in self._fargs['expression']:
            self._compile = jmespath.compile(self._fargs['expression'])
            del self._fargs['expression']

    def run(self):
        self._fargs['value'] = self.value
        fargs                = self._fargs.copy()

        if self._compile:
            expr = self._compile
        else:
            fargs['expression'] = self.build_args(fargs['expression'])
            expr = jmespath.compile(fargs.pop('expression'))

        return expr.search(**fargs)


if __name__ != "__main__":
    def _start():
        FILTERS.register(CovenantJMESPathFilter)
    _start()
