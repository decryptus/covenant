# -*- coding: utf-8 -*-
"""Real queues/callbacks and concurrent callers without an HTTP interface."""

import ast
from concurrent.futures import ThreadPoolExecutor
import inspect
import time
import unittest

from covenant.classes import collection
from covenant.classes.collection import (CollectionService, CollectionTimeout,
                                         CollectionFailed, UnknownEndpoint,
                                         InvalidEndpointType, DEFAULT_RESULT_TIMEOUT)
from covenant.classes.plugins import CovenantEPTObject, CovenantEPTSync


class CollectionServiceTests(unittest.TestCase):
    def setUp(self):
        self.endpoint = CovenantEPTSync('test', 'metric')
        self.service = CollectionService({'test': self.endpoint}, CovenantEPTObject, 1)

    def collect(self):
        return self.service.collect('test', 'metric', 'metrics', {'endpoint': 'test'})

    def test_legacy_job_contract_and_success(self):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.collect)
            obj = self.endpoint.qget(timeout=1)
            self.assertEqual(obj.get_endpoint(), 'test')
            self.assertEqual(obj.get_method(), 'metrics')
            self.assertEqual(obj.get_params(), {'endpoint': 'test'})
            self.assertEqual(obj.get_args(), {})
            obj.set_result(b'up 1\n')
            obj()
            self.assertEqual(future.result(timeout=1), b'up 1\n')
            self.assertIsNone(obj.callback.__self__.result)

    def test_timeout_and_late_callback_release_result(self):
        self.service.result_timeout = 0.05
        start = time.monotonic()
        with self.assertRaises(CollectionTimeout):
            self.collect()
        self.assertLess(time.monotonic() - start, 1)
        obj = self.endpoint.qget(timeout=1)
        completion = obj.callback.__self__
        self.assertTrue(completion.closed)
        obj.set_result(b'late payload')
        obj()
        self.assertIsNone(completion.result)
        self.assertFalse(completion.event.is_set())

    def test_plugin_error_remains_a_domain_error(self):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.collect)
            obj = self.endpoint.qget(timeout=1)
            obj.add_error('backend unavailable')
            obj()
            with self.assertRaisesRegex(CollectionFailed, 'backend unavailable'):
                future.result(timeout=1)

    def test_concurrent_results_do_not_cross_callers(self):
        self.service.result_timeout = 2
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(self.service.collect, 'test', 'metric',
                                       'metrics', {'target': str(i)}) for i in range(8)]
            jobs = [self.endpoint.qget(timeout=1) for _ in futures]
            self.assertEqual(len(set(obj.get_uid() for obj in jobs)), 8)
            for obj in reversed(jobs):
                obj.set_result(obj.get_params()['target'])
                obj()
            self.assertEqual([f.result(timeout=1) for f in futures], [str(i) for i in range(8)])

    def test_expired_call_does_not_contaminate_next_call(self):
        self.service.result_timeout = 0.05
        with self.assertRaises(CollectionTimeout):
            self.collect()
        expired = self.endpoint.qget(timeout=1)
        self.service.result_timeout = 1
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.collect)
            current = self.endpoint.qget(timeout=1)
            expired.set_result(b'expired')
            expired()
            current.set_result(b'current')
            current()
            self.assertEqual(future.result(timeout=1), b'current')

    def test_duplicate_callback_keeps_first_result(self):
        def dispatch(obj):
            first = CovenantEPTObject('test', obj.uid, 'test', 'metrics', {}, {}, obj.callback)
            first.set_result(b'first')
            first()
            obj.set_result(b'duplicate')
            obj()
        self.endpoint.qput = dispatch
        self.assertEqual(self.collect(), b'first')

    def test_failed_submission_closes_callback(self):
        submitted = []
        def dispatch(obj):
            submitted.append(obj)
            raise RuntimeError('queue unavailable')
        self.endpoint.qput = dispatch
        with self.assertRaisesRegex(RuntimeError, 'queue unavailable'):
            self.collect()
        obj = submitted[0]
        obj.set_result(b'late')
        obj()
        self.assertTrue(obj.callback.__self__.closed)
        self.assertIsNone(obj.callback.__self__.result)

    def test_unknown_endpoint_and_wrong_type_do_not_enqueue(self):
        with self.assertRaises(UnknownEndpoint):
            self.service.collect('missing', 'metric', 'metrics', {})
        with self.assertRaises(InvalidEndpointType):
            self.service.collect('test', 'probe', 'probes', {})
        self.assertTrue(self.endpoint.queue.empty())

    def test_timeout_is_finite_and_positive(self):
        for value in (None, True, False, 0, -1, 'bad', float('nan'),
                      float('inf'), float('-inf'), collection.MAX_RESULT_TIMEOUT * 2):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    CollectionService({}, CovenantEPTObject, value)
        self.assertEqual(CollectionService({}, CovenantEPTObject).result_timeout, DEFAULT_RESULT_TIMEOUT)
        self.assertEqual(CollectionService({}, CovenantEPTObject, '0.5').result_timeout, 0.5)

    def test_service_has_no_interface_imports(self):
        tree = ast.parse(inspect.getsource(collection))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or '')
        for name in imports:
            self.assertFalse(name.startswith(('httpdis', 'dwho', 'covenant.modules',
                                              'argparse', 'curses')))
