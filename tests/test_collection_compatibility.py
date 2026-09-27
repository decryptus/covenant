# -*- coding: utf-8 -*-
"""Historical module signatures, overrides, result shape and bounded cleanup."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from httpdis.httpdis import HttpReqError

from covenant.classes.plugins import CovenantEPTSync, EPTS_SYNC
from covenant.modules.metrics import MetricsModule
from covenant.modules.probes import ProbesModule

MODULE_TYPES = ((MetricsModule, 'metric', 'metrics'), (ProbesModule, 'probe', 'probes'))


class CollectionCompatibilityTests(unittest.TestCase):
    def module(self, module_class, kind, timeout=1):
        endpoint = CovenantEPTSync('test', kind)
        EPTS_SYNC['test'] = endpoint
        module = module_class()
        module.config = {'general': {'lock_timeout': 1, 'result_timeout': timeout}}
        module.lock_timeout = 1
        module._init_collection()
        return module, endpoint

    def setUp(self):
        self.registry_patch = patch.dict(EPTS_SYNC, clear=True)
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)

    def test_split_methods_preserve_uid_params_args_and_result_shape(self):
        for module_class, kind, method in MODULE_TYPES:
            with self.subTest(module=module_class.__name__):
                module, endpoint = self.module(module_class, kind)
                uid = module._push_epts_sync('test', method, {'target': 'file'}, {'extra': 2})
                obj = endpoint.qget(timeout=1)
                self.assertEqual(obj.get_uid(), uid)
                self.assertEqual(obj.get_method(), method)
                self.assertEqual(obj.get_params(), {'target': 'file'})
                self.assertEqual(obj.get_args(), {'extra': 2})
                obj.set_result(b'value 1\n')
                module._set_result(obj)
                self.assertIs(module.results[uid], obj)
                self.assertEqual(module._get_result(uid), {'error': None, 'result': b'value 1\n'})
                self.assertEqual(dict(module.results), {})

    def test_plugin_errors_keep_legacy_dictionary_instead_of_raising(self):
        for module_class, kind, method in MODULE_TYPES:
            with self.subTest(module=module_class.__name__):
                module, endpoint = self.module(module_class, kind)
                uid = module._push_epts_sync('test', method, {})
                obj = endpoint.qget(timeout=1)
                obj.add_error('failed')
                obj()
                self.assertEqual(module._get_result(uid), {'error': ['failed'], 'result': None})

    def test_historical_http_errors(self):
        for module_class, kind, method in MODULE_TYPES:
            with self.subTest(module=module_class.__name__):
                module, endpoint = self.module(module_class, kind)
                with self.assertRaises(HttpReqError) as caught:
                    module._push_epts_sync('missing', method, {})
                self.assertEqual(caught.exception.code, 404)
                endpoint.type = 'wrong'
                with self.assertRaises(HttpReqError) as caught:
                    module._push_epts_sync('test', method, {})
                self.assertEqual(caught.exception.code, 400)

    def test_timeout_late_callbacks_and_unknown_ids(self):
        for module_class, kind, method in MODULE_TYPES:
            with self.subTest(module=module_class.__name__):
                module, endpoint = self.module(module_class, kind, 0.02)
                uid = module._push_epts_sync('test', method, {})
                obj = endpoint.qget(timeout=1)
                with self.assertRaises(HttpReqError) as caught:
                    module._get_result(uid)
                self.assertEqual(caught.exception.code, 504)
                obj.set_result(b'late')
                obj()
                self.assertEqual(dict(module.results), {})
                self.assertEqual(module._collection_calls.pending, {})
                with self.assertRaises(HttpReqError) as caught:
                    module._get_result('unknown')
                self.assertEqual(caught.exception.code, 504)

    def test_abandoned_pending_and_completed_jobs_expire_without_further_calls(self):
        module, endpoint = self.module(ProbesModule, 'probe', 0.04)
        module._push_epts_sync('test', 'probes', {})
        second = module._push_epts_sync('test', 'probes', {})
        endpoint.qget(timeout=1)
        obj = endpoint.qget(timeout=1)
        obj.set_result(b'unclaimed')
        obj()
        self.assertIn(second, module.results)
        worker = module._collection_calls.worker
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(module._collection_calls.pending, {})
        self.assertIsNone(module._collection_calls.worker)

    def test_result_mapping_writes_wake_waiter(self):
        module, endpoint = self.module(ProbesModule, 'probe')
        uid = module._push_epts_sync('test', 'probes', {})
        obj = endpoint.qget(timeout=1)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(module._get_result, uid)
            obj.set_result(b'written')
            module.results[uid] = obj
            self.assertEqual(future.result(timeout=1), {'error': None, 'result': b'written'})

    def test_request_dispatch_preserves_subclass_overrides(self):
        for base, kind, method in MODULE_TYPES:
            with self.subTest(module=base.__name__):
                calls = []
                class Extended(base):
                    def _push_epts_sync(self, *args, **kwargs):
                        calls.append('push')
                        return super()._push_epts_sync(*args, **kwargs)
                    def _set_result(self, obj):
                        calls.append('set')
                        self.results[obj.get_uid()] = obj
                    def _get_result(self, uid):
                        calls.append('get')
                        return super()._get_result(uid)
                module, endpoint = self.module(Extended, kind)
                def complete(obj):
                    obj.set_result(b'metric 1\n')
                    obj()
                endpoint.qput = complete
                request = SimpleNamespace(query_params=lambda: {'endpoint': 'test'})
                response = getattr(module, method)(request)
                self.assertEqual(response.data, b'metric 1\n')
                self.assertEqual(calls, ['push', 'set', 'get'])

    def test_submit_failure_cleans_pending_calls(self):
        module, endpoint = self.module(ProbesModule, 'probe')
        with patch.object(endpoint, 'qput', side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):
                module._push_epts_sync('test', 'probes', {})
        self.assertEqual(module._collection_calls.pending, {})

    def test_out_of_order_results_do_not_cross_callers(self):
        module, endpoint = self.module(ProbesModule, 'probe')
        uids = [module._push_epts_sync('test', 'probes', {'target': str(i)}) for i in range(8)]
        jobs = [endpoint.qget(timeout=1) for _ in uids]
        worker = module._collection_calls.worker
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(module._get_result, uid) for uid in uids]
            for obj in reversed(jobs):
                obj.set_result(obj.get_params()['target'])
                obj()
            self.assertEqual([f.result(timeout=1)['result'] for f in futures], [str(i) for i in range(8)])
        worker.join(timeout=1)
        self.assertEqual(module._collection_calls.pending, {})
