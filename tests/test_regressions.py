# -*- coding: utf-8 -*-
"""Regression checks for certificate, file and metric collection failures."""

import os
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from prometheus_client import Gauge, generate_latest

from covenant.classes.collect import CovenantCollect
from covenant.classes.controls import CovenantCtrlLabelize
from covenant.classes.exceptions import CovenantTargetFailed
from covenant.classes.filters import CovenantNoResult
from covenant.classes.target import CovenantRegistry
from covenant.plugins.pfilestat import CovenantFilestatPlugin
from covenant.plugins.pssl import CovenantSslPlugin


class ExceptionTests(unittest.TestCase):
    def test_exception_message_and_arguments_are_preserved(self):
        original = OSError(2, 'missing file')
        wrapped = CovenantTargetFailed(original)
        self.assertEqual(wrapped.args, (str(original), original.args))

    def test_text_message_and_explicit_arguments_are_preserved(self):
        wrapped = CovenantTargetFailed('failed', ('target',))
        self.assertEqual(wrapped.args, ('failed', ('target',)))


class CertificateTests(unittest.TestCase):
    def test_valid_der_certificate_is_loaded_as_binary(self):
        key = rsa.generate_private_key(65537, 2048, default_backend())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u'localhost')])
        now = datetime.utcnow()
        cert = (x509.CertificateBuilder()
                .subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(1234)
                .not_valid_before(now - timedelta(days=1))
                .not_valid_after(now + timedelta(days=1))
                .sign(key, hashes.SHA256(), default_backend()))

        loaded, result = CovenantSslPlugin._load_cert(
            cert.public_bytes(serialization.Encoding.DER))

        self.assertEqual(loaded.serial_number, 1234)
        self.assertTrue(result['connect_success'])
        self.assertFalse(result['cert_has_expired'])
        self.assertEqual(result['cert_cn'], 'localhost')


class FileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.path = os.path.join(self.directory, u'\u00e9tat.pid')
        with open(self.path, 'w') as stream:
            stream.write('1234\n')
        self.plugin = CovenantFilestatPlugin('test-files')

    def tearDown(self):
        shutil.rmtree(self.directory)

    def test_included_file_exists(self):
        result = self.plugin._result({
            'path': self.path,
            'include_paths': ['^' + re.escape(self.path) + '$']})
        self.assertTrue(result['exists'])

    def test_excluded_file_is_rejected(self):
        with self.assertRaises(ValueError):
            self.plugin._result({
                'path': self.path,
                'exclude_paths': ['^' + re.escape(self.path) + '$']})

    def test_file_outside_include_list_is_rejected(self):
        with self.assertRaises(ValueError):
            self.plugin._result({'path': self.path, 'include_paths': ['^/other/']})

    def test_dynamic_traversal_and_outgoing_links_are_rejected(self):
        allowed = os.path.join(self.directory, 'allowed')
        os.mkdir(allowed)
        link = os.path.join(allowed, 'link')
        os.symlink(self.path, link)
        parent_link = os.path.join(allowed, 'parent')
        os.symlink(self.directory, parent_link)
        for follow in (False, True):
            for path in (link, os.path.join(parent_link, os.path.basename(self.path)),
                         os.path.join(allowed, '..', os.path.basename(self.path))):
                with self.subTest(path=path, follow=follow), self.assertRaises(ValueError):
                    self.plugin._result({'include_paths': '^' + re.escape(allowed) + '/',
                                         'follow': follow}, path)

    def test_missing_disallowed_paths_fail_before_reporting_absence(self):
        missing = self.path + '.missing'
        for rules in ({'include_paths': '^/other/'}, {'exclude_paths': re.escape(missing)}):
            with self.assertRaises(ValueError):
                self.plugin._result(rules, missing)

    def test_deny_rule_applies_to_symlink_destination(self):
        link = self.path + '.link'
        os.symlink(self.path, link)
        for follow in (False, True):
            with self.assertRaises(ValueError):
                self.plugin._result({'exclude_paths': re.escape(self.path) + '$',
                                     'follow': follow}, link)

    def test_link_replaced_between_resolution_and_inspection(self):
        link = self.path + '.link'
        outside = self.path + '.outside'
        with open(outside, 'w') as stream:
            stream.write('private')
        os.symlink(self.path, link)
        original = self.plugin._entry

        def swap(path, expected, follow):
            os.unlink(link)
            os.symlink(outside, link)
            return original(path, expected, follow)

        with patch.object(self.plugin, '_entry', swap), self.assertRaises(ValueError):
            self.plugin._result({'include_paths': re.escape(self.path) + r'(\.link)?$',
                                 'follow': True}, link)

    def test_broken_link_with_parent_segment_does_not_invent_a_file(self):
        link = self.path + '.link'
        os.symlink(os.path.join('absent-dir', '..', os.path.basename(self.path)), link)
        result = self.plugin._result({'include_paths': re.escape(self.directory) + '/',
                                      'follow': True}, link)
        self.assertFalse(result['exists'])

    def test_allowed_directory_alias_and_link_metadata(self):
        real = os.path.join(self.directory, 'run')
        alias = os.path.join(self.directory, 'var-run')
        os.mkdir(real)
        os.symlink(real, alias)
        pidfile = os.path.join(real, 'sshd.pid')
        os.rename(self.path, pidfile)
        os.symlink('sshd.pid', os.path.join(real, 'current'))
        policy = '^' + re.escape(self.directory) + '/(var-run|run)/(sshd[.]pid|current)$'
        for follow in (False, True):
            result = self.plugin._result({'include_paths': policy, 'follow': follow},
                                         os.path.join(alias, 'current'))
            self.assertTrue(result['exists'])
            self.assertEqual(result['islnk'], not follow)
            if not follow:
                self.assertEqual(result['lnk_target'], b'sshd.pid')
                self.assertEqual(result['lnk_source'], os.fsencode(pidfile))
        os.remove(pidfile)
        result = self.plugin._result({'include_paths': policy}, os.path.join(alias, 'current'))
        self.assertTrue(result['islnk'])
        self.assertFalse(result['readable'])

    def test_portable_lookup_observes_allowed_link_and_denies_excluded_target(self):
        link = self.path + '.link'
        os.symlink(self.path, link)
        with patch.object(os, 'supports_dir_fd', set()):
            for follow in (False, True):
                cfg = {'include_paths': re.escape(self.directory) + '/', 'follow': follow}
                self.assertTrue(self.plugin._result(dict(cfg), link)['readable'])
                cfg['exclude_paths'] = re.escape(self.path) + '$'
                with self.assertRaises(ValueError):
                    self.plugin._result(cfg, link)

    def test_unrestricted_file_still_exists(self):
        self.assertTrue(self.plugin._result({'path': self.path})['exists'])

    def test_missing_allowed_file_reports_absence(self):
        path = self.path + '.missing'
        result = self.plugin._result({
            'path': path, 'include_paths': ['^' + re.escape(path) + '$']})
        self.assertFalse(result['exists'])


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.registry = CovenantRegistry()
        self.gauge = Gauge('test_value', 'Test value', registry=self.registry)

    def collector(self, on_noresult=None, tasks=None):
        return CovenantCollect(
            'test_value', self.gauge, method='set',
            validator=lambda value: isinstance(value, (int, float)),
            value_tasks=tasks or [lambda value: value.get('value', CovenantNoResult())],
            on_noresult=on_noresult)

    def test_final_missing_result_replaces_previous_value(self):
        collect = self.collector(on_noresult={'value': 0})
        collect({'value': 7})
        collect({})
        self.assertIn(b'test_value 0.0\n', generate_latest(self.registry))

    def test_final_missing_result_removes_metric_and_can_recover(self):
        collect = self.collector()
        collect({'value': 7})
        collect({})
        self.assertNotIn(b'test_value', generate_latest(self.registry))
        collect({'value': 8})
        self.assertIn(b'test_value 8.0\n', generate_latest(self.registry))

    def test_missing_intermediate_result_skips_remaining_tasks(self):
        calls = []
        collect = self.collector(on_noresult={'value': 0}, tasks=[
            lambda value: CovenantNoResult(),
            lambda value: calls.append(value)])
        collect({})
        self.assertEqual(calls, [])
        self.assertIn(b'test_value 0.0\n', generate_latest(self.registry))

    def test_successful_result_is_preserved(self):
        self.collector()({'value': 7})
        self.assertIn(b'test_value 7.0\n', generate_latest(self.registry))


class LabelFilterTests(unittest.TestCase):
    def test_explicit_exclusion_survives_nonmatching_exclude_regex(self):
        self.assertTrue(CovenantCtrlLabelize._to_remove('secret', {
            'exclude': ['secret'], 'exclude_regex': '^other$'}))

    def test_explicit_exclusion_survives_matching_include_regex(self):
        self.assertTrue(CovenantCtrlLabelize._to_remove('secret', {
            'exclude': ['secret'], 'include_regex': '^secret$'}))

    def test_include_list_cannot_be_overridden_by_regex(self):
        self.assertTrue(CovenantCtrlLabelize._to_remove('secret', {
            'include': ['public'], 'include_regex': '.*'}))

    def test_include_regex_cannot_be_overridden_by_exclude_regex(self):
        self.assertTrue(CovenantCtrlLabelize._to_remove('secret', {
            'include_regex': '^public$', 'exclude_regex': '^other$'}))

    def test_allowed_key_survives_all_filters(self):
        self.assertFalse(CovenantCtrlLabelize._to_remove('public', {
            'include': ['public'], 'exclude': ['secret'],
            'include_regex': '^public$', 'exclude_regex': '^secret$'}))

    def test_matching_exclude_regex_removes_key(self):
        self.assertTrue(CovenantCtrlLabelize._to_remove('secret', {
            'exclude_regex': '^secret$'}))

    def test_no_filters_keeps_key(self):
        self.assertFalse(CovenantCtrlLabelize._to_remove('public', {}))


if __name__ == '__main__':
    unittest.main()
