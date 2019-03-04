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

from sonicprobe import helpers

from covenant.classes.exceptions import CovenantTaskError, CovenantTargetFailed
from covenant.classes.filters import CovenantNoResult

LOG = logging.getLogger('covenant.collect')


class CovenantCollect(object):
    def __init__(self,
                 name,
                 metric,
                 method      = None,
                 validator   = None,
                 value       = None,
                 default     = None,
                 labels      = None,
                 value_tasks = None,
                 on_fail     = None,
                 on_noresult = None):
        self.name        = name
        self.metric      = metric
        self.method      = method
        self.validator   = validator
        self.value       = value
        self.default     = default
        self.labels      = labels
        self.value_tasks = value_tasks

        self._orig       = {'on_fail':     on_fail,
                            'on_noresult': on_noresult}

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

    def set_labels_metric(self, labels, metricvalue):
        method = getattr(self.metric.labels(**labels), self.method)
        try:
            method(metricvalue)
        except Exception, e:
            LOG.exception("metric: %r, labels: %r, metricvalue: %r, error: %r",
                          self.name,
                          labels,
                          metricvalue,
                          e)
            raise

    def _build_labels_metrics(self):
        nb_labels   = len(self.labels)
        nb_values   = 0
        labels      = {}

        for label in self.labels:
            if label.removed() \
               or not label.labelvalues:
                continue

            xlen = len(label.labelvalues)
            if xlen > nb_values:
                nb_values = xlen

            r = []

            for labelvalue in label.labelvalues:
                if isinstance(labelvalue.labelvalue, CovenantNoResult):
                    self.remove(True)
                    del labels
                    return

                if nb_labels == 1:
                    self.set_labels_metric({labelvalue.labelname: labelvalue.labelvalue},
                                           labelvalue.get())
                else:
                    r.append(labelvalue)

            if nb_labels > 1:
                if label.labelname not in labels:
                    labels[label.labelname] = r
                else:
                    labels[label.labelname].extend(r)
                    xlen = len(labels[label.labelname])
                    if xlen > nb_values:
                        nb_values = xlen

        if nb_labels > 1:
            for n in range(0, nb_values):
                r = {}
                v = None
                for labelname in self.metric._labelnames:
                    if len(labels[labelname]) <= n:
                        ref = labels[labelname][-1]
                    else:
                        ref = labels[labelname][n]

                    r[labelname] = ref.labelvalue
                    metricvalue  = ref.get()
                    if metricvalue is not None:
                        v = metricvalue
                self.set_labels_metric(r, v)

        if nb_values == 0:
            self.remove(True)

        del labels

    def _get_value_from_tasks(self, data):
        if isinstance(data, CovenantTargetFailed):
            if self.on_fail['remove']:
                self.remove(True)
                return
            return copy.copy(self.on_fail['value'])

        for task in self.value_tasks:
            if isinstance(data, CovenantNoResult):
                if self.on_noresult['remove']:
                    self.remove(True)
                    return
                data = self.on_noresult['value']
                break
            data = task(value = data)

        return data

    def _sanitize_value(self, data):
        if isinstance(data, CovenantTargetFailed):
            if self.on_fail['remove']:
                self.remove(True)
                return
            data = self.on_fail['value']

        if self.default is not None and data is None:
            data = self.default

        return data

    def __call__(self, data):
        self.remove(False)
        if not isinstance(data, CovenantTargetFailed) \
           and self.value is not None:
            data = self.value

        data = copy.copy(data)

        if self.labels:
            for label in self.labels:
                if self._orig['on_fail']:
                    label.set_on_fail(self._orig['on_fail'])
                if self._orig['on_noresult']:
                    label.set_on_noresult(self._orig['on_noresult'])

                label.task_label(data)
                try:
                    label.task_value(data, self.value_tasks, self.value, self.default)
                except CovenantTaskError, e:
                    LOG.warning("%s. (metric: %r, labelname: %r)", e, self.name, label.labelname)
        elif self.value_tasks:
            data = self._get_value_from_tasks(data)

        try:
            if self.removed():
                return

            data = self._sanitize_value(data)

            if self.removed():
                return

            if self.labels:
                self._build_labels_metrics()
            elif self.validator(data):
                getattr(self.metric, self.method)(data)
            else:
                LOG.warning("unable to fetch a valid metricvalue. (metric: %r, data: %r)", self.name, data)
        except Exception, e:
            LOG.exception("metric: %r, data: %r, error: %r", self.name, data, e)
            raise
        finally:
            del data
