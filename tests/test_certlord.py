"""CertLord snapshot and transport contracts, without live credentials."""
import os
import tempfile
import unittest
from unittest.mock import patch

from covenant.services.certlord import snapshot_metrics, InvalidObservation
from covenant.plugins.certlord import CovenantCertlordPlugin
from covenant.classes.exceptions import CovenantConfigurationError
from covenant.classes.plugins import CovenantEPTObject

UUID = '12345678-1234-4234-8234-123456789abc'
EMPTY = '''# TYPE certlord_observation_completed_timestamp_seconds gauge
certlord_observation_completed_timestamp_seconds 1791040000
# TYPE certlord_certificates_observed gauge
certlord_certificates_observed 0
'''
FULL = EMPTY.replace('certificates_observed 0', 'certificates_observed 1') + '''# TYPE certlord_certificate_info gauge
certlord_certificate_info{certificate_id="%s",origin="external",renewal_owner="external",status="deployed",pending_action="none",material_state="readable"} 1
# TYPE certlord_certificate_not_after_timestamp_seconds gauge
certlord_certificate_not_after_timestamp_seconds{certificate_id="%s"} 1793040000
# TYPE certlord_certificate_tls_verification gauge
certlord_certificate_tls_verification{certificate_id="%s",status="not_checked"} 1
''' % (UUID, UUID, UUID)


def plugin(directory, **kwargs):
    cfg = {'url': 'http://127.0.0.1:9876/api/certificates/metrics', 'timeout': 1}
    cfg.update(kwargs)
    result = CovenantCertlordPlugin('certlord-test')
    result.init({'general': {'result_timeout': 30, 'server_id': 'test'},
                 'covenant': {'config_dir': directory},
                 'metrics': [{'name': 'certlord', 'config': cfg, 'collects': []}]})
    result.safe_init()
    return result


def request(params=None):
    return CovenantEPTObject('test', 'test:1', 'test', 'metrics', params or {}, {}, lambda obj: None)


class SnapshotTests(unittest.TestCase):
    def test_external_and_empty_inventory(self):
        self.assertIn(b'certlord_certificate_not_after', snapshot_metrics(FULL))
        self.assertNotIn(b'certlord_certificate_info{', snapshot_metrics(EMPTY))

    def test_acme_retry_is_current_gauge(self):
        text = FULL.replace('"external"', '"acme"').replace('pending_action="none"', 'pending_action="renew"')
        with self.assertRaises(InvalidObservation):
            snapshot_metrics(text)
        text += '# TYPE certlord_certificate_issuance_retry_count gauge\ncertlord_certificate_issuance_retry_count{certificate_id="%s"} 3\n' % UUID
        self.assertIn(b'} 3.0', snapshot_metrics(text))

    def test_reject_partial_inventory_and_expiry(self):
        for text in (FULL.replace('certificates_observed 1', 'certificates_observed 2'),
                     FULL.replace('material_state="readable"', 'material_state="missing"'),
                     EMPTY.replace('certificates_observed 0', 'certificates_observed NaN'),
                     EMPTY.replace('1791040000', '+Inf')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                snapshot_metrics(text)

    def test_reject_duplicate_invalid_identity_and_labels(self):
        for text in (FULL + 'certlord_certificate_tls_verification{certificate_id="%s",status="failed"} 1\n' % UUID,
                     FULL.replace(UUID, 'not-a-uuid'),
                     FULL.replace('origin="external"', 'origin="secret"')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                snapshot_metrics(text)

    def test_does_not_forward_unknown_metrics_or_help(self):
        result = snapshot_metrics(EMPTY + '# HELP private_secret SECRET\n# TYPE private_secret gauge\nprivate_secret 42\n')
        self.assertNotIn(b'SECRET', result)
        self.assertNotIn(b'private_secret', result)

    def test_stale_time_is_preserved_for_prometheus(self):
        self.assertIn(b' 10.0\n', snapshot_metrics(EMPTY.replace('1791040000', '10')))


class TransportTests(unittest.TestCase):
    def setUp(self):
        from covenant.classes.plugins import EPTS_SYNC
        previous = EPTS_SYNC.copy()
        self.addCleanup(lambda: (EPTS_SYNC.clear(), EPTS_SYNC.update(previous)))

    def test_startup_rejects_unsafe_configuration(self):
        cases = ({'url': 'http://remote.example/metrics'}, {'timeout': 0},
                 {'timeout': float('nan')}, {'timeout': 15}, {'unknown': 1},
                 {'url': 'https://user:pass@host/metrics'},
                 {'url': 'https://host/metrics?token=secret'},
                 {'url': 'https://host/metrics'})
        for cfg in cases:
            with self.subTest(cfg=cfg), self.assertRaises((CovenantConfigurationError, ValueError)):
                plugin('/tmp', **cfg)

    def test_success_failure_recovery_and_no_cached_values(self):
        collector = plugin('/tmp')
        with patch('covenant.plugins.certlord.requests.Session') as factory:
            session = factory.return_value.__enter__.return_value
            response = session.get.return_value.__enter__.return_value
            response.status_code = 200
            response.iter_content.return_value = [FULL.encode()]
            self.assertIn(b'source_up 1', collector._do_call(request()))
            self.assertFalse(session.trust_env)
            self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
            self.assertTrue(session.get.call_args.kwargs['verify'])
            for status in (302, 401, 403, 503):
                response.status_code = status
                output = collector._do_call(request())
                self.assertIn(b'source_up 0', output)
                self.assertNotIn(b'certlord_certificate_', output)
            response.status_code = 200
            response.iter_content.return_value = [EMPTY.encode()]
            self.assertIn(b'source_up 1', collector._do_call(request()))

    def test_rotated_token_and_fixed_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'reader.token')
            collector = plugin(directory, token_file='reader.token')
            with patch('covenant.plugins.certlord.requests.Session') as factory:
                session = factory.return_value.__enter__.return_value
                response = session.get.return_value.__enter__.return_value
                response.status_code = 200
                response.iter_content.return_value = [EMPTY.encode()]
                for token in ('first-token', 'rotated-token'):
                    with open(path, 'w') as stream:
                        stream.write(token + '\n')
                    self.assertIn(b'source_up 1', collector._do_call(request()))
                    self.assertEqual(session.get.call_args.kwargs['headers']['Authorization'], 'Bearer ' + token)
                with self.assertRaises(CovenantConfigurationError):
                    collector._do_call(request({'target': 'https://untrusted.example'}))

    def test_limits_and_malformed_response_are_unavailable(self):
        collector = plugin('/tmp')
        with patch('covenant.plugins.certlord.requests.Session') as factory:
            response = factory.return_value.__enter__.return_value.get.return_value.__enter__.return_value
            response.status_code = 200
            for data in (b'garbage', b'x' * (4 * 1024 * 1024 + 1), b'\xff'):
                response.iter_content.return_value = [data]
                self.assertIn(b'source_up 0', collector._do_call(request()))


class RuntimeTests(unittest.TestCase):
    def test_real_yaml_worker_source_and_httpdis(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'certlord_runtime.py')],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('CertLord runtime integration OK', result.stdout)
