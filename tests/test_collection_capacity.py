"""Bounded admission and expiration before plugin execution."""
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from covenant.classes import collection
from covenant.classes.collection import CollectionBusy, CollectionCalls, CollectionService, monotonic
from covenant.classes.plugins import (CovenantEPTObject, CovenantEPTSync,
    CovenantPlugBase, EPTS_SYNC, MAX_PENDING_COLLECTIONS)
from covenant.modules.metrics import MetricsModule
from covenant.modules.probes import ProbesModule
from httpdis.httpdis import HttpReqError


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.endpoint = CovenantEPTSync('capacity-test', 'metric')
        self.service = CollectionService({'capacity-test': self.endpoint}, CovenantEPTObject, 1)

    def close_calls(self, calls):
        with calls.condition:
            worker = calls.worker
            calls.pending.clear()
            calls.condition.notify_all()
        if worker is not None:
            worker.join(1)
            self.assertFalse(worker.is_alive())

    def test_completed_results_fill_capacity_until_consumed_or_deleted(self):
        for cls, kind, method in ((MetricsModule, 'metric', 'metrics'),
                                  (ProbesModule, 'probe', 'probes')):
            endpoint = CovenantEPTSync('capacity-test', kind)
            module = cls()
            module.config = {'general': {'result_timeout': 30}}
            with patch.dict(EPTS_SYNC, {'capacity-test': endpoint}):
                module._init_collection()
                calls = module._collection_calls
                self.addCleanup(self.close_calls, calls)
                uids = []
                for index in range(collection.MAX_PENDING_RESULTS):
                    uids.append(module._push_epts_sync('capacity-test', method, {}))
                    obj = endpoint.qget(timeout=1)
                    obj.set_result(index)
                    obj()
                self.assertTrue(endpoint.queue.empty())
                with self.assertRaises(HttpReqError) as caught:
                    module._push_epts_sync('capacity-test', method, {})
                self.assertEqual(caught.exception.code, 503)
                self.assertEqual(len(calls.pending), collection.MAX_PENDING_RESULTS)
                self.assertEqual(module._get_result(uids[0]), {'error': None, 'result': 0})
                module._push_epts_sync('capacity-test', method, {})
                del module.results[uids[1]]
                module._push_epts_sync('capacity-test', method, {})
                self.assertEqual(len(calls.pending), collection.MAX_PENDING_RESULTS)
                self.assertEqual(module.results[uids[-1]].get_result(), len(uids) - 1)

    def test_concurrent_completed_calls_cannot_overfill_shared_result_store(self):
        second = CovenantEPTSync('other', 'metric')
        endpoints = {'capacity-test': self.endpoint, 'other': second}
        calls = CollectionCalls(CollectionService(endpoints, CovenantEPTObject, 30))
        self.addCleanup(self.close_calls, calls)
        def complete(obj):
            obj.set_result(obj.uid)
            obj()
        def submit(index):
            endpoint = 'other' if index % 2 else 'capacity-test'
            try:
                return calls.submit(endpoint, 'metric', 'metrics', {})
            except CollectionBusy:
                return None
        with patch.object(self.endpoint, 'qput', complete), patch.object(second, 'qput', complete):
            with ThreadPoolExecutor(max_workers=8) as pool:
                accepted = list(pool.map(submit, range(collection.MAX_PENDING_RESULTS * 2)))
        uids = [uid for uid in accepted if uid is not None]
        self.assertEqual(len(uids), collection.MAX_PENDING_RESULTS)
        self.assertEqual(set(calls.pending), set(uids))
        for uid in uids:
            self.assertEqual(calls.result(uid), {'error': None, 'result': uid})
        self.assertEqual(calls.pending, {})

    def test_expiration_frees_result_capacity_and_late_callback_stays_ignored(self):
        calls = CollectionCalls(self.service)
        self.addCleanup(self.close_calls, calls)
        now = [100.0]
        with patch.object(collection, 'MAX_PENDING_RESULTS', 1), \
                patch.object(collection, 'monotonic', side_effect=lambda: now[0]):
            first = calls.submit('capacity-test', 'metric', 'metrics', {})
            old = self.endpoint.qget(timeout=1)
            with self.assertRaises(CollectionBusy):
                calls.submit('capacity-test', 'metric', 'metrics', {})
            now[0] += 2
            second = calls.submit('capacity-test', 'metric', 'metrics', {})
            old.set_result(b'late')
            old()
            self.assertNotIn(first, calls.pending)
            self.assertEqual(set(calls.pending), {second})
            self.assertIsNone(calls.pending[second].result)
            current = self.endpoint.qget(timeout=1)
            current.set_result(b'current')
            current()
            self.assertEqual(calls.result(second), {'error': None, 'result': b'current'})

    def test_failed_callback_does_not_kill_worker_or_retry_callback(self):
        for expired_first in (False, True):
            with self.subTest(expired_first=expired_first):
                seen, callbacks = [], []
                class Plugin(CovenantPlugBase):
                    PLUGIN_NAME = 'synthetic'
                    def _do_call(self, obj, targets=None, registry=None):
                        seen.append(obj.uid)
                        return b'ok'
                def fail(obj):
                    callbacks.append(obj.uid)
                    raise ValueError('synthetic private callback detail')
                def completed(obj):
                    callbacks.append(obj.uid)
                _, first = self.service.prepare('capacity-test', 'metric', 'metrics', {}, {}, fail)
                if expired_first:
                    first.deadline = monotonic() - 1
                _, second = self.service.prepare('capacity-test', 'metric', 'metrics', {}, {}, completed)
                second.deadline = monotonic() + 30
                for obj in (first, second):
                    self.endpoint.qput(obj)
                get, count = self.endpoint.qget, [0]
                def next_job(*args):
                    count[0] += 1
                    if count[0] > 2:
                        raise SystemExit()
                    return get(timeout=1)
                failures = []
                def run():
                    try:
                        Plugin('capacity-test').run()
                    except SystemExit:
                        pass
                    except BaseException as error:
                        failures.append(type(error).__name__)
                with patch.dict(EPTS_SYNC, {'capacity-test': self.endpoint}), \
                        patch.object(self.endpoint, 'qget', next_job), \
                        self.assertLogs('covenant.plugins', level='ERROR') as logs:
                    thread = threading.Thread(target=run, daemon=True)
                    thread.start(); thread.join(2)
                    self.assertFalse(thread.is_alive())
                self.assertEqual(failures, [])
                self.assertEqual(seen, [second.uid] if expired_first else [first.uid, second.uid])
                self.assertEqual(callbacks, [first.uid, second.uid])
                self.assertEqual(second.result, b'ok')
                self.assertNotIn('private callback detail', '\n'.join(logs.output))

    def test_full_queue_refuses_without_waiting_and_split_state_is_cleaned(self):
        for _ in range(MAX_PENDING_COLLECTIONS):
            self.endpoint.qput(object())
        calls = CollectionCalls(self.service)
        with self.assertRaises(CollectionBusy):
            calls.submit('capacity-test', 'metric', 'metrics', {})
        self.assertEqual(calls.pending, {})
        with self.assertRaises(CollectionBusy):
            self.service.collect('capacity-test', 'metric', 'metrics', {})
        self.assertEqual(self.endpoint.queue.qsize(), MAX_PENDING_COLLECTIONS)
        self.endpoint.qget(timeout=1)
        self.endpoint.qput(object())
        self.assertEqual(self.endpoint.queue.qsize(), MAX_PENDING_COLLECTIONS)

    def test_concurrent_producers_cannot_exceed_capacity(self):
        def submit(_):
            try:
                self.endpoint.qput(object())
                return True
            except CollectionBusy:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(submit, range(MAX_PENDING_COLLECTIONS * 2)))
        self.assertEqual(sum(accepted), MAX_PENDING_COLLECTIONS)
        self.assertEqual(self.endpoint.queue.qsize(), MAX_PENDING_COLLECTIONS)

    def test_expired_job_skips_plugin_and_next_job_executes(self):
        seen, completed = [], []
        class Plugin(CovenantPlugBase):
            PLUGIN_NAME = 'synthetic'
            def _do_call(self, obj, targets=None, registry=None):
                seen.append(obj.uid)
                return b'ok'
        plugin = Plugin('capacity-test')
        _, expired = self.service.prepare('capacity-test', 'metric', 'metrics', {}, {}, completed.append)
        expired.deadline = monotonic() - 1
        _, current = self.service.prepare('capacity-test', 'metric', 'metrics', {}, {}, completed.append)
        for obj in (expired, current):
            self.endpoint.qput(obj)
        get = self.endpoint.qget
        count = [0]
        def next_job(*args):
            count[0] += 1
            if count[0] > 2:
                raise SystemExit()
            return get(timeout=1)
        def run():
            try:
                plugin.run()
            except SystemExit:
                pass
        with patch.dict(EPTS_SYNC, {'capacity-test': self.endpoint}), patch.object(self.endpoint, 'qget', next_job):
            thread = threading.Thread(target=run, daemon=True)
            thread.start(); thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(seen, [current.uid])
        self.assertEqual(completed, [expired, current])
        self.assertTrue(expired.has_error())
        self.assertEqual(current.result, b'ok')

    def test_both_http_facades_report_overload_as_503(self):
        for cls, kind, method in ((MetricsModule, 'metric', 'metrics'),
                                  (ProbesModule, 'probe', 'probes')):
            endpoint = CovenantEPTSync('capacity-test', kind)
            for _ in range(MAX_PENDING_COLLECTIONS):
                endpoint.qput(object())
            module = cls()
            module.config = {'general': {'result_timeout': 1}}
            with patch.dict(EPTS_SYNC, {'capacity-test': endpoint}):
                module._init_collection()
                with self.assertRaises(HttpReqError) as caught:
                    module._push_epts_sync('capacity-test', method, {})
                self.assertEqual(caught.exception.code, 503)
                self.assertEqual(module._collection_calls.pending, {})
