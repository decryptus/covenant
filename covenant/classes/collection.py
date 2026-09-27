# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Endpoint collection orchestration, independent of HTTP and command interfaces."""

import logging
import math
import threading
import uuid
from collections import namedtuple
try:
    from collections.abc import MutableMapping
except ImportError:
    from collections import MutableMapping
try:
    from time import monotonic
except ImportError:  # Historical Python 2.7 runtime.
    from time import time as monotonic

DEFAULT_RESULT_TIMEOUT = 30.0
RESULT_WORKER_IDLE_TIMEOUT = 0.1
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

    def prepare(self, endpoint, endpoint_type, method, params, args, callback):
        if endpoint not in self.endpoints:
            raise UnknownEndpoint('unable to find endpoint: %r' % endpoint)
        ept_sync = self.endpoints[endpoint]
        if ept_sync.type != endpoint_type:
            raise InvalidEndpointType('invalid endpoint type, correct type: %r' % ept_sync.type)

        uid = '%s:%s' % (ept_sync.name, uuid.uuid4())
        return ept_sync, self.object_factory(ept_sync.name, uid, endpoint, method,
                                             params, args, callback)

    def collect(self, endpoint, endpoint_type, method, params, args = None):
        completion = _Completion()
        ept_sync, obj = self.prepare(endpoint, endpoint_type, method, params, args,
                                     completion.complete)
        uid = obj.get_uid()
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


_PendingCall = namedtuple('_PendingCall', 'deadline result')


class CollectionResults(MutableMapping):
    """Compatibility mapping of completed, unconsumed calls."""

    def __init__(self, calls):
        self.calls = calls

    def __getitem__(self, uid):
        with self.calls.condition:
            self.calls._expire()
            call = self.calls.pending.get(uid)
            if call is None or call.result is None:
                raise KeyError(uid)
            return call.result

    def __setitem__(self, uid, obj):
        if uid != obj.get_uid():
            raise ValueError('result UID does not match its key')
        self.calls.complete(obj)

    def __delitem__(self, uid):
        with self.calls.condition:
            self[uid]
            del self.calls.pending[uid]
            self.calls.condition.notify_all()

    def __iter__(self):
        with self.calls.condition:
            self.calls._expire()
            return iter([uid for uid, call in self.calls.pending.items()
                         if call.result is not None])

    def __len__(self):
        return sum(1 for _ in self)

    def copy(self):
        with self.calls.condition:
            return dict(self)


class CollectionCalls(object):
    """Bounded split submission/retrieval API for historical module facades.

    At most one active expiry worker per instance, reused across adjacent calls.
    It also clears jobs whose caller never retrieves their result.
    """

    def __init__(self, service):
        self.service = service
        self.condition = threading.Condition()
        self.pending = {}
        self.results = CollectionResults(self)
        self.worker = None

    def _expire(self):
        now = monotonic()
        expired = [uid for uid, call in self.pending.items() if call.deadline <= now]
        for uid in expired:
            del self.pending[uid]
        if expired:
            self.condition.notify_all()

    def _reap(self):
        with self.condition:
            while True:
                self._expire()
                if not self.pending:
                    self.condition.wait(RESULT_WORKER_IDLE_TIMEOUT)
                    if not self.pending:
                        break
                if self.pending:
                    deadline = min(call.deadline for call in self.pending.values())
                    self.condition.wait(max(0, deadline - monotonic()))
            self.worker = None

    def submit(self, endpoint, endpoint_type, method, params, args = None, callback = None):
        queue, obj = self.service.prepare(endpoint, endpoint_type, method, params, args,
                                          callback or self.complete)
        uid = obj.get_uid()
        with self.condition:
            self._expire()
            self.pending[uid] = _PendingCall(monotonic() + self.service.result_timeout, None)
            if self.worker is None:
                self.worker = threading.Thread(target = self._reap, name = 'covenant-results')
                self.worker.daemon = True
                try:
                    self.worker.start()
                except BaseException:
                    self.worker = None
                    self.pending.pop(uid, None)
                    raise
            self.condition.notify_all()
        try:
            queue.qput(obj)
        except BaseException:
            with self.condition:
                self.pending.pop(uid, None)
                self.condition.notify_all()
            raise
        return uid

    def complete(self, obj):
        with self.condition:
            self._expire()
            uid = obj.get_uid()
            call = self.pending.get(uid)
            if call is not None and call.result is None:
                self.pending[uid] = _PendingCall(call.deadline, obj)
                self.condition.notify_all()

    def result(self, uid):
        with self.condition:
            try:
                while True:
                    self._expire()
                    call = self.pending.get(uid)
                    if call is None:
                        raise CollectionTimeout('collection result expired or unknown: %r' % uid)
                    if call.result is not None:
                        obj = call.result
                        if obj.has_error():
                            LOG.error('failed on call: %r. (errors: %r)', uid, obj.get_errors())
                            return {'error': obj.get_errors(), 'result': None}
                        LOG.info('successful on call: %r', uid)
                        return {'error': None, 'result': obj.get_result()}
                    self.condition.wait(max(0, call.deadline - monotonic()))
            finally:
                self.pending.pop(uid, None)
                self.condition.notify_all()
