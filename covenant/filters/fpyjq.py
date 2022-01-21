# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.filters.fpyjq"""

import logging
import pyjq

from covenant.classes.filters import CovenantFilterBase, FILTERS

LOG = logging.getLogger('covenant.filters.pyjq')

_ALLOWED_FUNCTIONS = ('all',
                      'compile',
                      'first',
                      'one')


class CovenantPyJqFilter(CovenantFilterBase):
    FILTER_NAME = 'pyjq'

    def init(self):
        func        = self.kwargs.get('func') or 'first'
        self._fargs = self.kwargs

        if 'func' in self._fargs:
            del self._fargs['func']

        if func not in _ALLOWED_FUNCTIONS:
            raise ValueError("pyjq function not allowed: %r" % func)

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
