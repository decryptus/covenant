# -*- coding: utf-8 -*-
"""pyjq filter"""

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
import pyjq

from covenant.classes.filters import CovenantFilterBase, FILTERS

LOG = logging.getLogger('covenant.filters.pyjq')


class CovenantPyJqFilter(CovenantFilterBase):
    FILTER_NAME = 'pyjq'

    def init(self):
        func        = self.kwargs.get('func') or 'first'
        self._fargs = self.kwargs

        if 'func' in self._fargs:
            del self._fargs['func']

        self._func = getattr(pyjq, func)

    def run(self):
        self._fargs['value'] = self.value

        if 'vars' not in self._fargs:
            self._fargs['vars'] = {}

        fargs           = self._fargs.copy()
        fargs['vars']   = self.get_vars(fargs['vars'])
        fargs['script'] = self.build_args(fargs['script'], fargs['vars'])

        return self._func(**fargs)


if __name__ != "__main__":
    def _start():
        FILTERS.register(CovenantPyJqFilter)
    _start()
