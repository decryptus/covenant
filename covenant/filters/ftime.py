# -*- coding: utf-8 -*-
# Copyright (C) 2018-2019 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.filters.ftime"""

import logging
import time

from covenant.classes.filters import CovenantFilterBase, FILTERS

LOG = logging.getLogger('covenant.filters.time')


class CovenantTimeFilter(CovenantFilterBase):
    FILTER_NAME = 'time'

    def init(self):
        funcs       = self.kwargs.pop('func')
        self._funcs = []

        if not isinstance(funcs, list):
            funcs = [funcs]

        for func in funcs:
            if func.startswith('_'):
                raise ValueError("time function not allowed: %r" % func)
            self._funcs.append(getattr(time, func))

        self._fargs         = list(self.kwargs.get('args', []) or [])
        self._value_arg_pos = int(self.kwargs.get('value_arg_pos') or 0)

    def run(self):
        fargs = list(self._fargs)
        fargs.insert(self._value_arg_pos, self.value)

        for func in self._funcs:
            fargs = [func(*fargs)]

        return fargs.pop(0)


if __name__ != "__main__":
    def _start():
        FILTERS.register(CovenantTimeFilter)
    _start()
