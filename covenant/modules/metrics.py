# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.modules.metrics"""

import gc
import logging
import time
import uuid

from dwho.classes.modules import DWhoModuleBase, MODULES
from httpdis.httpdis import HttpReqError, HttpResponse
from sonicprobe.libs import xys
from sonicprobe.libs.moresynchro import RWLock

from covenant.classes.plugins import CovenantEPTObject, EPTS_SYNC, generate_latest
from covenant.classes.covenant_collector import CovenantCollector

LOG = logging.getLogger('covenant.modules.metrics')


# pylint: disable=attribute-defined-outside-init
class MetricsModule(DWhoModuleBase):
    MODULE_NAME     = 'metrics'

    LOCK            = RWLock()

    def safe_init(self, options):
        self.results      = {}
        self.lock_timeout = self.config['general']['lock_timeout']
        CovenantCollector()

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
        elif EPTS_SYNC[endpoint].type != 'metric':
            raise HttpReqError(400, "invalid endpoint type, correct type: %r" % EPTS_SYNC[endpoint].type)

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
    target*: !!str
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
        except HttpReqError:
            raise
        except Exception as e:
            LOG.exception(e)
        finally:
            gc.collect()
            self.LOCK.release()

    def server(self, request): # pylint: disable-msg=unused-argument
        if not self.LOCK.acquire_read(self.lock_timeout):
            raise HttpReqError(503, "unable to take LOCK for reading after %s seconds" % self.lock_timeout)

        try:
            return HttpResponse(data = generate_latest())
        except HttpReqError:
            raise
        except Exception as e:
            LOG.exception(e)
        finally:
            self.LOCK.release()


if __name__ != "__main__":
    def _start():
        MODULES.register(MetricsModule())
    _start()
