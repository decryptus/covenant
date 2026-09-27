# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Historical HTTP module methods, delegated to the collection service."""

from httpdis.httpdis import HttpReqError

from covenant.classes.collection import (CollectionCalls, CollectionService,
                                          DEFAULT_RESULT_TIMEOUT, UnknownEndpoint,
                                          InvalidEndpointType, CollectionTimeout)
from covenant.classes.plugins import CovenantEPTObject, EPTS_SYNC

COLLECTION_HTTP_ERRORS = {
    UnknownEndpoint: 404,
    InvalidEndpointType: 400,
    CollectionTimeout: 504,
}
COLLECTION_EXCEPTIONS = tuple(COLLECTION_HTTP_ERRORS)


class CollectionModuleCompat(object):
    def _init_collection(self):
        self.collection = CollectionService(
            EPTS_SYNC, CovenantEPTObject,
            self.config['general'].get('result_timeout', DEFAULT_RESULT_TIMEOUT))
        self._collection_calls = CollectionCalls(self.collection)
        self.results = self._collection_calls.results

    def _push_epts_sync(self, endpoint, method, params, args = None):
        try:
            return self._collection_calls.submit(endpoint, self.ENDPOINT_TYPE, method,
                                                  params, args, self._set_result)
        except COLLECTION_EXCEPTIONS as error:
            raise HttpReqError(COLLECTION_HTTP_ERRORS[type(error)], str(error))

    def _set_result(self, obj):
        self._collection_calls.complete(obj)

    def _get_result(self, uid):
        try:
            return self._collection_calls.result(uid)
        except CollectionTimeout as error:
            raise HttpReqError(504, str(error))
