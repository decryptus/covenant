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


from covenant.modules.collection import CollectionModuleCompat

LOG = logging.getLogger('covenant.modules.probes')


# pylint: disable=attribute-defined-outside-init
class ProbesModule(CollectionModuleCompat, DWhoModuleBase):
    MODULE_NAME     = 'probes'
    ENDPOINT_TYPE   = 'probe'

    LOCK            = RWLock()

    def safe_init(self, options):
        self._init_collection()
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
            uid = self._push_epts_sync(params['endpoint'], 'probes', params)
            result = self._get_result(uid)
            if result['error']:
                raise HttpReqError(500, "failed to get results. (errors: %r)" % result['error'])
            return HttpResponse(data = result['result'])
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
