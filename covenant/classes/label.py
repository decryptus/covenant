# -*- coding: utf-8 -*-
# Copyright (C) 2018-2019 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.classes.label"""

import copy
import logging

from sonicprobe import helpers

from covenant.classes.exceptions import CovenantTaskError, CovenantTargetFailed
from covenant.classes.filters import CovenantNoResult

LOG = logging.getLogger('covenant.label')


class CovenantLabelValue(object): # pylint: disable=useless-object-inheritance
    def __init__(self, labelname = None, labelvalue = None, labeldefault = None, metricvalue = None, remove = False):
        self.labelname    = labelname
        self.labelvalue   = labelvalue
        self.labeldefault = labeldefault
        self.metricvalue  = metricvalue
        self._removed     = bool(remove)

        if labelvalue is None:
            self.labelvalue = self.labeldefault
        elif isinstance(labelvalue, (list, tuple, set)):
            if labelvalue:
                self.labelvalue = list(labelvalue)[0]
            else:
                self.labelvalue = self.labeldefault
        elif isinstance(labelvalue, dict):
            if labelvalue:
                self.labelvalue = labelvalue.popitem()[1]
            else:
                self.labelvalue = self.labeldefault

    def set(self, metricvalue):
        self.metricvalue = metricvalue
        return self

    def get(self):
        return self.metricvalue

    def remove(self, val = True):
        self._removed = bool(val)
        return self

    def removed(self):
        return self._removed

    def vars(self):
        return {'__labelname':    self.labelname,
                '__labelvalue':   self.labelvalue,
                '__labeldefault': self.labeldefault}


class CovenantLabelValuesCollection(list):
    pass


class CovenantLabels(object): # pylint: disable=useless-object-inheritance
    def __init__(self,
                 labelname,
                 labelvalues  = None,
                 labeldefault = None,
                 labelstatic  = True,
                 label_tasks  = None,
                 value_tasks  = None,
                 on_fail      = None,
                 on_noresult  = None):
        self.labelname    = labelname
        self.labelvalues  = []
        self.labeldefault = labeldefault
        self.labelstatic  = labelstatic
        self.label_tasks  = label_tasks
        self.value_tasks  = value_tasks
        self._removed     = False
        self._orig        = {'on_fail': on_fail,
                             'on_noresult': on_noresult}

        self.on_fail      = self._on(on_fail)
        self.on_noresult  = self._on(on_noresult)

        if labelvalues is not None:
            if not isinstance(labelvalues, list):
                labelvalues = [labelvalues]

            for labelvalue in labelvalues:
                self.labelvalues.append(CovenantLabelValue(labelname,
                                                           labelvalue,
                                                           labeldefault))
    @staticmethod
    def _on(cfg):
        default = {'labelvalue': None,
                   'value':      None,
                   'remove':     True}

        if isinstance(cfg, dict):
            default['remove'] = False
            default.update(cfg)
        elif cfg not in (None, 'remove'):
            default['remove'] = False

        return default.copy()

    def set_on_fail(self, cfg):
        if not self._orig['on_fail']:
            self.on_fail = self._on(cfg)

    def set_on_noresult(self, cfg):
        if not self._orig['on_noresult']:
            self.on_noresult = self._on(cfg)

    def labels(self):
        r = {}
        for labelvalue in self.labelvalues:
            r[labelvalue.labelname] = labelvalue.labelvalue
        return r

    def remove(self, val = True):
        self._removed = bool(val)
        return self

    def removed(self):
        return self._removed

    def task_label(self, data):
        self.remove(False)
        if self.labelstatic:
            return self

        (failed, noresult) = (False, False)

        if isinstance(data, CovenantTargetFailed):
            if self.on_fail['remove']:
                return self.remove(True)
            failed   = True
            data     = self.on_fail['labelvalue']
        elif isinstance(data, CovenantNoResult):
            if self.on_noresult['remove']:
                return self.remove(True)
            noresult = True
            data     = self.on_noresult['labelvalue']

        self.labelvalues = []
        nvalues          = []
        values           = copy.copy(data)

        if not isinstance(values, list):
            values = [values]

        if not self.label_tasks:
            nvalues = values
        elif not failed and not noresult:
            nolabelvalue = False

            for value in values:
                if nolabelvalue or isinstance(value, CovenantNoResult):
                    if self.on_noresult['remove']:
                        return self.remove(True)
                    nolabelvalue = True
                    break

                for task in self.label_tasks:
                    if isinstance(value, CovenantNoResult):
                        if self.on_noresult['remove']:
                            return self.remove(True)
                        nolabelvalue = True
                        break

                    value = task(value = value)

                if not isinstance(value, CovenantLabelValuesCollection):
                    nvalues.append(value)
                else:
                    nvalues.extend(value)

            if nolabelvalue:
                nvalues = [self.on_noresult['labelvalue']]

        for value in nvalues:
            if not isinstance(value, CovenantLabelValue):
                self.labelvalues.append(CovenantLabelValue(self.labelname,
                                                           value,
                                                           self.labeldefault))
            elif not value.removed():
                value.labelname    = self.labelname
                value.labeldefault = self.labeldefault
                self.labelvalues.append(value)

        del values

        return self

    def task_value(self, data, value_tasks = None, collect_value = None, collect_default = None):
        tasks = value_tasks or self.value_tasks
        (failed, noresult) = (False, False)

        if isinstance(data, CovenantTargetFailed):
            if self.on_fail['remove']:
                return self.remove(True)
            failed   = True
            data     = copy.copy(self.on_fail['value'])
        elif isinstance(data, CovenantNoResult):
            if self.on_noresult['remove']:
                return self.remove(True)
            noresult = True
            data     = copy.copy(self.on_noresult['value'])

        value = None

        for labelvalue in self.labelvalues:
            value = copy.copy(data)
            if not failed and not noresult and tasks:
                for task in tasks:
                    if isinstance(value, CovenantNoResult):
                        if self.on_noresult['remove']:
                            return self.remove(True)
                        value = self.on_noresult['value']
                        break
                    value = task(value = value, labelvalue = labelvalue)
            if isinstance(value, CovenantNoResult):
                if self.on_noresult['remove']:
                    return self.remove(True)
                value = self.on_noresult['value']
            if helpers.is_scalar(value):
                labelvalue.set(value)
            elif collect_value is not None:
                labelvalue.set(collect_value)
            elif collect_default is not None:
                labelvalue.set(collect_default)
            elif tasks:
                raise CovenantTaskError("unable to fetch metricvalue for labelvalue: %r" % labelvalue.labelvalue)

        del value

        return self
