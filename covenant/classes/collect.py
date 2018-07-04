# -*- coding: utf-8 -*-
"""covenant collect"""

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

import copy
import logging

from covenant.classes.exceptions import CovenantTargetFailed
from covenant.classes.filters import CovenantNoResult

LOG = logging.getLogger('covenant.collect')


class CovenantCollect(object):
    def __init__(self,
                 name,
                 metric,
                 method      = None,
                 value       = None,
                 default     = None,
                 labels      = None,
                 value_tasks = None,
                 on_fail     = None,
                 on_noresult = None):
        self.name        = name
        self.metric      = metric
        self.method      = method
        self.value       = value
        self.default     = default
        self.labels      = labels
        self.value_tasks = value_tasks

        self.on_fail     = self._on(on_fail)
        self.on_noresult = self._on(on_noresult)

    def _on(self, cfg):
        default = {'value':  None,
                   'remove': True}

        if isinstance(cfg, dict):
            default['remove'] = False
            default.update(cfg)
        elif cfg not in (None, 'remove'):
            default['remove'] = False

        return default.copy()

    def remove(self, val = True):
        setattr(self.metric, '_removed', bool(val))
        return self

    def removed(self):
        return getattr(self.metric, '_removed', False)

    def __call__(self, data):
        self.remove(False)
        if not isinstance(data, CovenantTargetFailed) \
           and self.value is not None:
            data = self.value

        data = copy.copy(data)

        if self.labels:
            for label in self.labels:
                label.task_label(data)
                label.task_value(data, self.value_tasks)
        elif self.value_tasks:
            if isinstance(data, CovenantTargetFailed):
                if self.on_fail['remove']:
                    self.remove(True)
                    return
                data = copy.copy(self.on_fail['value'])
            else:
                for task in self.value_tasks:
                    if isinstance(data, CovenantNoResult):
                        if self.on_noresult['remove']:
                            self.remove(True)
                            return
                        data = self.on_noresult['value']
                        break
                    data = task(value = data)

        if isinstance(data, CovenantTargetFailed):
            if self.on_fail['remove']:
                self.remove(True)
                return
            data = self.on_fail['value']

        if self.default is not None and data is None:
            data = self.default

        if not self.labels:
            try:
                getattr(self.metric, self.method)(data)
            except Exception, e:
                LOG.exception("metric: %r, data: %r, error: %r", self.name, data, e)
                raise
            del data
            return

        has_label = False

        for label in self.labels:
            if label.removed() or not label.labelvalues:
                continue

            has_label = True

            for labelvalue in label.labelvalues:
                method = getattr(self.metric.labels(
                                    **{labelvalue.labelname: labelvalue.labelvalue}),
                                    self.method)

                try:
                    method(labelvalue.get())
                except Exception, e:
                    LOG.exception("metric: %r, labelname: %r, labelvalue: %r, data: %r, error: %r",
                                  self.name,
                                  labelvalue.labelname,
                                  labelvalue.labelvalue,
                                  labelvalue.get(),
                                  e)
                    raise

        if not has_label:
            self.remove(True)

        del data

