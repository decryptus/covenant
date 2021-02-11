# -*- coding: utf-8 -*-
# Copyright (C) 2018-2021 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.filters.fjmespath"""

import logging
import jmespath

from covenant.classes.filters import CovenantFilterBase, CovenantNoResult, FILTERS

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

        ret = expr.search(**fargs)
        if ret is None:
            return CovenantNoResult()

        return ret


if __name__ != "__main__":
    def _start():
        FILTERS.register(CovenantJMESPathFilter)
    _start()
