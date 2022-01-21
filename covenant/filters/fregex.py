# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.filters.fregex"""

import logging
import re
import six

from covenant.classes.filters import CovenantFilterBase, CovenantNoResult, FILTERS

LOG = logging.getLogger('covenant.filters.regex')

_MATCH_OBJECT_FUNCS = ('match', 'search')


class CovenantRegexFilter(CovenantFilterBase):
    FILTER_NAME = 'regex'

    @classmethod
    def _parse_flags(cls, flags):
        if isinstance(flags, int):
            return flags

        if isinstance(flags, list):
            r = 0
            for x in flags:
                r |= cls._parse_flags(x)
            return r

        if isinstance(flags, six.string_types):
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

        if func.startswith('_'):
            raise ValueError("regex function not allowed: %r" % func)

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
