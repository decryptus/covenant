# -*- coding: utf-8 -*-
"""metrics module"""

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

import json
import gc
import logging
import requests
import time
import uuid

from dwho.classes.modules import DWhoModuleBase, MODULES
from covenant.classes.plugins import CovenantEPTObject, EPTS_SYNC
from sonicprobe import helpers
from sonicprobe.libs import network, urisup, xys
from sonicprobe.libs.moresynchro import RWLock
from sonicprobe.libs.http_json_server import HttpReqError, HttpResponse

LOG = logging.getLogger('covenant.modules.metrics')


class MetricsModule(DWhoModuleBase):
    MODULE_NAME     = 'metrics'

    LOCK            = RWLock()

    def safe_init(self, options):
        self.results      = {}
        self.lock_timeout = self.config['general']['lock_timeout']

    def _set_result(self, obj):
        self.results[obj.get_uid()] = obj

    def _get_result(self, uid):
        r = {'error':  None,
             'result': None}

        while True:
            if uid not in self.results:
                time.sleep(0.1)
                continue

            res = self.results.pop(uid)
            if res.has_error():
                r['error'] = res.get_errors()
                LOG.error("failed on call: %r. (errors: %r)", res.get_uid(), r['error'])
            else:
                r['result'] = res.get_result()
                LOG.info("successful on call: %r", res.get_uid())
                LOG.debug("result on call: %r", r['result'])

            return r

    def _push_epts_sync(self, endpoint, method, params, args = None):
        if endpoint not in EPTS_SYNC:
            raise HttpReqError(404, "unable to find endpoint: %r" % endpoint)

        ept_sync  = EPTS_SYNC[endpoint]
        uid       = "%s:%s" % (ept_sync.name, uuid.uuid4())
        ept_sync.qput(CovenantEPTObject(ept_sync.name,
                                         uid,
                                         endpoint,
                                         method,
                                         params,
                                         args,
                                         self._set_result))
        return uid


    METRICS_QSCHEMA = xys.load("""
    endpoint: !!str
    """)

    def metrics(self, request):
        params = request.query_params()

        if not isinstance(params, dict):
            raise HttpReqError(400, "invalid arguments type")

        if not xys.validate(params, self.METRICS_QSCHEMA):
            raise HttpReqError(415, "invalid arguments for command")

        if not self.LOCK.acquire_read(self.lock_timeout):
            raise HttpReqError(503, "unable to take LOCK for reading after %s seconds" % self.lock_timeout)

        try:
            uid = self._push_epts_sync(params['endpoint'], 'metrics', params)
            res = self._get_result(uid)
            if res['error']:
                raise HttpReqError(500, "failed to get results. (errors: %r)" % res['error'])

            return HttpResponse(data = res['result'])
        except HttpReqError, e:
            raise
        except Exception, e:
            LOG.exception("%r", e)
        finally:
            gc.collect()
            self.LOCK.release()


if __name__ != "__main__":
    def _start():
        MODULES.register(MetricsModule())
    _start()
