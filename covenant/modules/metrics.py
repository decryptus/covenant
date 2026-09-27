# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.modules.metrics"""

import gc
import logging

from dwho.classes.modules import DWhoModuleBase, MODULES
from httpdis.httpdis import HttpReqError, HttpResponse
from sonicprobe.libs import xys
from sonicprobe.libs.moresynchro import RWLock

from covenant.classes.plugins import CovenantEPTObject, EPTS_SYNC, generate_latest
from covenant.classes.covenant_collector import CovenantCollector

from covenant.classes.collection import (CollectionService, DEFAULT_RESULT_TIMEOUT,
                                          UnknownEndpoint, InvalidEndpointType,
                                          CollectionFailed, CollectionTimeout)

COLLECTION_HTTP_ERRORS = {
    UnknownEndpoint: 404,
    InvalidEndpointType: 400,
    CollectionFailed: 500,
    CollectionTimeout: 504,
}
COLLECTION_EXCEPTIONS = tuple(COLLECTION_HTTP_ERRORS)

LOG = logging.getLogger('covenant.modules.metrics')


# pylint: disable=attribute-defined-outside-init
class MetricsModule(DWhoModuleBase):
    MODULE_NAME     = 'metrics'

    LOCK            = RWLock()

    def safe_init(self, options):
        self.collection = CollectionService(
            EPTS_SYNC, CovenantEPTObject,
            self.config['general'].get('result_timeout', DEFAULT_RESULT_TIMEOUT))
        self.lock_timeout = self.config['general']['lock_timeout']
        CovenantCollector()

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
            result = self.collection.collect(params['endpoint'], 'metric', 'metrics', params)
            return HttpResponse(data = result)
        except COLLECTION_EXCEPTIONS as error:
            raise HttpReqError(COLLECTION_HTTP_ERRORS[type(error)], str(error))
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
