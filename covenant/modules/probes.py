# -*- coding: utf-8 -*-
# Copyright (C) 2018-2022 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.modules.probes"""

import gc
import logging

from dwho.classes.modules import DWhoModuleBase, MODULES
from httpdis.httpdis import HttpReqError, HttpResponse
from sonicprobe.libs import xys
from sonicprobe.libs.moresynchro import RWLock

from covenant.classes.plugins import CovenantEPTObject, EPTS_SYNC

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

LOG = logging.getLogger('covenant.modules.probes')


# pylint: disable=attribute-defined-outside-init
class ProbesModule(DWhoModuleBase):
    MODULE_NAME     = 'probes'

    LOCK            = RWLock()

    def safe_init(self, options):
        self.collection = CollectionService(
            EPTS_SYNC, CovenantEPTObject,
            self.config['general'].get('result_timeout', DEFAULT_RESULT_TIMEOUT))
        self.lock_timeout = self.config['general']['lock_timeout']

    PROBES_QSCHEMA = xys.load("""
    endpoint: !!str
    target*: !!str
    """)

    def probes(self, request):
        params = request.query_params()

        if not isinstance(params, dict):
            raise HttpReqError(400, "invalid arguments type")

        if not xys.validate(params, self.PROBES_QSCHEMA):
            raise HttpReqError(415, "invalid arguments for command")

        if not self.LOCK.acquire_read(self.lock_timeout):
            raise HttpReqError(503, "unable to take LOCK for reading after %s seconds" % self.lock_timeout)

        try:
            result = self.collection.collect(params['endpoint'], 'probe', 'probes', params)
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


if __name__ != "__main__":
    def _start():
        MODULES.register(ProbesModule())
    _start()
