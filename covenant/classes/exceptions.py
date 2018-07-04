# -*- coding: utf-8 -*-
"""covenant exceptions"""

__author__  = "Adrien DELLE CAVE <adc@doowan.net>"
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

LOG = logging.getLogger('covenant.exceptions')


class CovenantConfigurationError(Exception):
    pass


class CovenantTargetFailed(Exception):
    def __init__(self, message = None, args = None):
        if isinstance(message, Exception):
            return Exception.__init__(self, message.message, message.args)
        else:
            return Exception.__init__(self, message, args)
