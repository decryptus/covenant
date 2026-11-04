"""HTTP credential rules and redirect behavior over real local sockets."""
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

from covenant.classes.exceptions import CovenantConfigurationError
from covenant.classes.plugins import CovenantEPTObject
from covenant.classes.target import CovenantTarget
from covenant.plugins.http import CovenantHttpPlugin
from covenant.services.credential_targets import CredentialTargets


@contextmanager
def upstream():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get('Authorization'), self.headers.get('X-Key')))
            self.send_response(302 if self.server.location else 200)
            if self.server.location:
                self.send_header('Location', self.server.location)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    server.location = None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, 'http://127.0.0.1:%d' % server.server_port, seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class CredentialTests(unittest.TestCase):
    def test_rules(self):
        rules = CredentialTargets(['https://api.example.org', 'https://*.services.example.org',
                                   {'scheme': 'https', 'port': 443, 'regex': r'node[0-9]+\.example\.org'},
                                   {'scheme': 'https', 'port': 8443, 'cidr': '10.42.0.0/24'}])
        for value in ('https://api.example.org/health', 'https://a.services.example.org',
                      'https://node42.example.org:443', 'https://10.42.0.17:8443'):
            self.assertTrue(rules.allows(value), value)
        for value in ('https://api.example.org.evil.test', 'https://api.example.org@evil.test',
                      'http://node42.example.org', 'https://a.b.services.example.org',
                      'https://node42.example.org.invalid', 'https://10.42.0.17'):
            self.assertFalse(rules.allows(value), value)
        for invalid in (None, '*', ['*', 'https://api.example.org'], [{'regex': '.+'}]):
            with self.assertRaises(CovenantConfigurationError):
                CredentialTargets(invalid)

    def test_dynamic_probe_and_redirects(self):
        plugin = CovenantHttpPlugin('credential-test')
        with upstream() as (server, first, calls), upstream() as (_, second, arrivals):
            server.location = second
            for rules, expected in (([first], (True, False)), ([second], (False, True)),
                                    (['*'], (True, True)), (None, (False, False))):
                config = {'headers': {'X-Key': 'test-key'}, 'timeout': 2}
                if rules is not None:
                    config['credential_targets'] = rules
                plugin.targets = [CovenantTarget('health', config, [], plugin.registry,
                                                  credentials={'username': 'test', 'password': 'test'})]
                request = CovenantEPTObject('test', 'test:1', 'test', 'probes',
                                            {'target': first}, {}, lambda obj: None)
                plugin.do_probes(request)
                for received, allowed in zip((calls[-1], arrivals[-1]), expected):
                    self.assertEqual(bool(received[1]), allowed)
                    self.assertEqual(received[2], 'test-key' if allowed else None)
