# -*- coding: utf-8 -*-
# Copyright (C) 2018-2021 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.classes.covenant_collector"""

import logging

from dwho.config import get_softname, get_softver
from packaging import version
from prometheus_client.core import GaugeMetricFamily, REGISTRY

LOG = logging.getLogger('covenant.modules.metrics')


class CovenantCollector(object):
    def __init__(self, registry = REGISTRY):
        self._metrics = [
            self._add_metric('version_info', "%s version." % get_softname(), self._info()),
            self._add_metric('up', "Could %s server be reached." % get_softname(), {})
        ]

        if registry:
            registry.register(self)

    @staticmethod
    def _add_metric(name, documentation, data):
        labels = data.keys()
        values = [data[k] for k in labels]
        g = GaugeMetricFamily(name, documentation, labels=labels)
        g.add_metric(values, 1)
        return g

    def collect(self):
        return self._metrics

    @staticmethod
    def _info():
        ver = get_softver()
        release = (version.parse(get_softver()).release or tuple()) + (0, 0, 0)

        return {
            "version": str(ver),
            "major": str(release[0]),
            "minor": str(release[1]),
            "patchlevel": str(release[2])
        }
