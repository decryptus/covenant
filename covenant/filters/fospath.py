# -*- coding: utf-8 -*-
# Copyright (C) 2018-2020 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.filters.fospath"""

import os.path

import logging

from covenant.classes.filters import CovenantFilterBase, FILTERS


LOG = logging.getLogger('covenant.filters.ospath')

_ALLOWED_FUNCTIONS = ('abspath',
                      'basename',
                      'dirname',
                      'exists',
                      'expanduser',
                      'getatime',
                      'getctime',
                      'getmtime',
                      'getsize',
                      'isabs',
                      'isdir',
                      'isfile',
                      'islink',
                      'ismount',
                      'join',
                      'lexists',
                      'normcase',
                      'normpath',
                      'realpath',
                      'relpath',
                      'split',
                      'splitdrive',
                      'splitext')


class CovenantOsPathFilter(CovenantFilterBase):
    FILTER_NAME = 'ospath'

    def init(self):
        funcs       = self.kwargs.pop('func')
        self._funcs = []

        if not isinstance(funcs, list):
            funcs = [funcs]

        for func in funcs:
            if func not in _ALLOWED_FUNCTIONS:
                raise ValueError("os.path function not allowed: %r" % func)

            self._funcs.append(getattr(os.path, func))

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
        FILTERS.register(CovenantOsPathFilter)
    _start()
