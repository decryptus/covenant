# -*- coding: utf-8 -*-
# Copyright (C) 2018-2019 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.classes.exceptions"""

import logging

LOG = logging.getLogger('covenant.exceptions')


class CovenantConfigurationError(Exception):
    pass


class CovenantTargetFailed(Exception):
    def __init__(self, message = None, args = None):
        if isinstance(message, Exception):
            Exception.__init__(self, message.message, message.args)
        else:
            Exception.__init__(self, message, args)

class CovenantTaskError(Exception):
    pass
