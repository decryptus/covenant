# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Endpoint collection orchestration, independent of HTTP and command interfaces."""

import logging
import math
import threading
import uuid

DEFAULT_RESULT_TIMEOUT = 30.0
MAX_RESULT_TIMEOUT = getattr(threading, 'TIMEOUT_MAX', 2147483.0)
LOG = logging.getLogger('covenant.collection')


class CollectionError(Exception):
    """A collection could not be completed."""


class UnknownEndpoint(CollectionError):
    pass


class InvalidEndpointType(CollectionError):
    pass


class CollectionFailed(CollectionError):
    pass


class CollectionTimeout(CollectionError):
    pass


def validate_result_timeout(value):
    """Reject values that would disable or overflow a bounded wait."""
    if isinstance(value, bool):
        raise ValueError('result_timeout must be a finite positive number of seconds')
    try:
        timeout = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('result_timeout must be a finite positive number of seconds')
    if math.isnan(timeout) or math.isinf(timeout) or not 0 < timeout <= MAX_RESULT_TIMEOUT:
        raise ValueError('result_timeout must be a finite positive number of seconds')
    return timeout


class _Completion(object):
    """One call owns its result; closed calls ignore late or duplicate callbacks."""

    def __init__(self):
        self.event = threading.Event()
        self.lock = threading.Lock()
        self.result = None
        self.closed = False

    def complete(self, obj):
        with self.lock:
            if not self.closed and not self.event.is_set():
                self.result = obj
                self.event.set()

    def wait(self, timeout):
        ready = self.event.wait(timeout)
        with self.lock:
            self.closed = True
            result = self.result if ready else None
            self.result = None
        if not ready:
            raise CollectionTimeout('collection result unavailable after %s seconds' % timeout)
        return result

    def close(self):
        with self.lock:
            self.closed = True
            self.result = None


class CollectionService(object):
    """Dispatch plain parameters using the existing plugin job/callback contract."""

    def __init__(self, endpoints, object_factory, result_timeout = DEFAULT_RESULT_TIMEOUT):
        self.endpoints = endpoints
        self.object_factory = object_factory
        self.result_timeout = validate_result_timeout(result_timeout)

    def collect(self, endpoint, endpoint_type, method, params, args = None):
        if endpoint not in self.endpoints:
            raise UnknownEndpoint('unable to find endpoint: %r' % endpoint)
        ept_sync = self.endpoints[endpoint]
        if ept_sync.type != endpoint_type:
            raise InvalidEndpointType('invalid endpoint type, correct type: %r' % ept_sync.type)

        uid = '%s:%s' % (ept_sync.name, uuid.uuid4())
        completion = _Completion()
        obj = self.object_factory(ept_sync.name, uid, endpoint, method,
                                  params, args, completion.complete)
        try:
            # CovenantEPTSync uses an unbounded Queue: submission does not wait
            # for capacity. The finite wait includes time spent queued for a worker.
            ept_sync.qput(obj)
            result = completion.wait(self.result_timeout)
            if result.has_error():
                LOG.error('failed on call: %r. (errors: %r)', uid, result.get_errors())
                raise CollectionFailed('failed to get results. (errors: %r)' % result.get_errors())
            LOG.info('successful on call: %r', uid)
            LOG.debug('result on call: %r', result.get_result())
            return result.get_result()
        finally:
            completion.close()
