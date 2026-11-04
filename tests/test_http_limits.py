"""HTTP plugin limits over loopback, using both fixed and dynamic destinations."""
import gzip
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

from covenant.classes.exceptions import CovenantConfigurationError, CovenantTargetFailed
from covenant.plugins.http import CovenantHttpPlugin, _response_limits
from test_templates import request, template


class LimitHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/slow':
            self.server.release.wait(3)
            self.close_connection = True
            return
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', '/json')
            self.send_header('Content-Length', '100000000')
            self.end_headers()
            # No redirect body arrives. Following it must not wait for the body.
            self.server.release.wait(3)
            return
        body = b'1234'
        self.send_response(200)
        if self.path == '/gzip':
            body = gzip.compress(b'a' * 4096)
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class HttpLimitTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), LimitHandler)
        self.server.release = threading.Event()
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.release.set)
        self.origin = 'http://127.0.0.1:%d' % self.server.server_port

    def fetch(self, path, limit, dynamic=False, **config):
        plugin = CovenantHttpPlugin('limit-test')
        url = self.origin + path
        config['max_response_bytes'] = limit
        if not dynamic:
            config['url'] = url
        target = Mock(credentials=None, config=config)
        plugin.targets = [target]
        plugin._do_call(request(url if dynamic else None))
        return target.call_args[0][0]

    def test_exact_limit_and_overflow_without_content_length(self):
        for dynamic in (True, False):
            with self.subTest(dynamic=dynamic):
                with self.assertLogs('covenant.plugins.http'):
                    self.assertIsInstance(self.fetch('/text', 3, dynamic), CovenantTargetFailed)
                self.assertEqual(self.fetch('/text', 4, dynamic), '1234')

    def test_compressed_payload_limit_applies_to_decoded_bytes(self):
        with self.assertLogs('covenant.plugins.http'):
            self.assertIsInstance(self.fetch('/gzip', 64), CovenantTargetFailed)
        self.assertEqual(self.fetch('/gzip', 4096), 'a' * 4096)

    def test_redirect_body_is_discarded_before_json_decoding(self):
        for dynamic in (True, False):
            self.assertEqual(self.fetch('/redirect', 4, dynamic, timeout=0.5, format='json'), 1234)

    def test_slow_upstream_and_recovery(self):
        with self.assertLogs('covenant.plugins.http'):
            self.assertIsInstance(self.fetch('/slow', 4, timeout=0.1), CovenantTargetFailed)
        self.assertEqual(self.fetch('/text', 4), '1234')

    def test_configuration_limits(self):
        self.assertEqual(_response_limits({}), (10, 4194304))
        self.assertEqual(_response_limits({'timeout': None}), (10, 4194304))
        self.assertEqual(_response_limits({'timeout': '0.5', 'max_response_bytes': 1}), (0.5, 1))
        for key, invalid in (('timeout', [True, 'nan', 'inf', 0, -1, 'invalid']),
                             ('max_response_bytes', [True, None, 0, -1, 0.5, '4'])):
            for value in invalid:
                with self.subTest(key=key, value=value), self.assertRaises(CovenantConfigurationError):
                    _response_limits({key: value})
        for name in ('nginx', 'apache', 'rabbitmq'):
            for target in template('metrics.d/%s.yml' % name, {'max_response_bytes': 4096}):
                self.assertEqual(target['config']['max_response_bytes'], 4096)
