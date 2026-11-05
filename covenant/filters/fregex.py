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
_FLAG_NAMES = ('A', 'ASCII', 'DEBUG', 'I', 'IGNORECASE', 'L', 'LOCALE',
               'M', 'MULTILINE', 'NOFLAG', 'S', 'DOTALL', 'T', 'TEMPLATE',
               'U', 'UNICODE', 'X', 'VERBOSE')
_FLAGS = {name: int(getattr(re, name)) for name in _FLAG_NAMES if hasattr(re, name)}
_FLAG_MASK = 0
for _flag in _FLAGS.values():
    _FLAG_MASK |= _flag


class CovenantRegexFilter(CovenantFilterBase):
    FILTER_NAME = 'regex'

    @classmethod
    def _parse_flags(cls, flags):
        if isinstance(flags, list):
            combined = 0
            for value in flags:
                combined |= cls._parse_flags(value)
            return combined

        if isinstance(flags, six.string_types):
            if flags in _FLAGS:
                return _FLAGS[flags]
            if flags.isdigit():
                flags = int(flags)

        if (isinstance(flags, six.integer_types) and not isinstance(flags, bool)
                and flags >= 0 and not (int(flags) & ~_FLAG_MASK)):
            return int(flags)
        raise ValueError("invalid regex flags: expected flag names or a supported integer mask")

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

        if 'flags' in self._fargs:
            flags = self._fargs['flags']
            self._fargs['flags'] = 0 if flags is None else self._parse_flags(flags)

        if 'pattern' in self._fargs:
            flags = self._fargs.pop('flags', 0)
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
