# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.filters.fbuiltintypes"""

import six

from covenant.classes.filters import CovenantFilterBase, CovenantNoResult, FILTERS


# Configuration can only select these operations, even if a new Python version
# adds public methods. Keep version-dependent methods only where callable.
_READ_METHODS = (
    'as_integer_ratio', 'bit_count', 'bit_length', 'capitalize', 'casefold',
    'center', 'conjugate', 'copy', 'count', 'decode', 'difference', 'encode',
    'endswith', 'expandtabs', 'find', 'from_bytes', 'fromhex', 'fromkeys',
    'get', 'has_key', 'hex', 'index', 'indices', 'intersection', 'is_integer',
    'isalnum', 'isalpha', 'isascii', 'isdecimal', 'isdigit', 'isdisjoint',
    'isidentifier', 'islower', 'isnumeric', 'isprintable', 'isspace',
    'issubset', 'issuperset', 'istitle', 'isupper', 'items', 'iteritems',
    'iterkeys', 'itervalues', 'join', 'keys', 'ljust', 'lower', 'lstrip',
    'maketrans', 'partition', 'removeprefix', 'removesuffix', 'replace',
    'rfind', 'rindex', 'rjust', 'rpartition', 'rsplit', 'rstrip', 'split',
    'splitlines', 'startswith', 'strip', 'swapcase', 'symmetric_difference',
    'title', 'to_bytes', 'translate', 'union', 'upper', 'values', 'viewitems',
    'viewkeys', 'viewvalues', 'zfill',
)
_FORMAT_METHODS = ('format', 'format_map')
_RECEIVER_TYPES = (six.binary_type, six.text_type, dict, list, tuple, float,
                   complex, set, frozenset, slice) + six.integer_types
_AVAILABLE_METHODS = frozenset(name for name in _READ_METHODS + _FORMAT_METHODS
                               if any(callable(getattr(kind, name, None))
                                      for kind in _RECEIVER_TYPES))


class CovenantBuiltinTypesFilter(CovenantFilterBase):
    FILTER_NAME = 'builtintypes'

    def init(self):
        self._func = self.kwargs.get('func')
        allow_format = self.kwargs.get('allow_format', False)
        if not isinstance(allow_format, bool):
            raise ValueError("builtintypes allow_format must be a boolean")
        if not isinstance(self._func, six.string_types) or self._func not in _AVAILABLE_METHODS:
            raise ValueError("builtintypes method not allowed: %r" % self._func)
        if self._func in _FORMAT_METHODS and not allow_format:
            raise ValueError("builtintypes %s requires allow_format: true on this task" % self._func)

        self._args = list(self.kwargs.get('args', []) or [])

    def run(self):
        fargs = self.build_args(list(self._args))

        value = self.value
        if self._func == 'get' and isinstance(value, (list, tuple)):
            if not value:
                return CovenantNoResult()
            if not fargs:
                return value[0]
            if len(fargs) == 1:
                return value[fargs[0]]
            return value[fargs[0]:fargs[1]]

        if self._func == 'join':
            return fargs[0].join(value)

        return getattr(value, self._func)(*fargs)


if __name__ != "__main__":
    def _start():
        FILTERS.register(CovenantBuiltinTypesFilter)
    _start()
