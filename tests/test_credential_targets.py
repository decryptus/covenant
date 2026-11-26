"""HTTP credential rules and redirect behavior over real local sockets."""
import os
import socket
from pathlib import Path
import tempfile
import threading
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import yaml
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

    def test_shared_rules_loaded_once_for_probes_and_metrics(self):
        with tempfile.TemporaryDirectory() as directory, upstream() as (_, first, calls), \
                upstream() as (_, second, arrivals), patch('covenant.classes.plugins.EPTS_SYNC'):
            path = Path(directory, 'shared.yml')
            path.write_text(yaml.safe_dump([first]))
            plugins = []
            for kind in ('metrics', 'probes'):
                plugin = CovenantHttpPlugin(kind)
                cfg = {'import_credential_targets': 'shared.yml', 'headers': {'X-Key': 'test'}}
                if kind == 'probes':
                    cfg['credential_targets'] = [second]
                plugin.config = {'allowed_targets': ['*'], 'covenant': {'config_dir': directory},
                                 kind: [{'name': 'health', 'config': cfg, 'collects': []}]}
                plugin.safe_init()
                plugins.append(plugin)
            path.unlink()
            for plugin in plugins:
                for url in (first, second):
                    request = CovenantEPTObject('test', 'test:1', 'test', plugin.name,
                                                {'target': url}, {}, lambda obj: None)
                    getattr(plugin, 'do_' + plugin.name)(request)
                self.assertEqual(calls[-1][2], 'test')
                self.assertEqual(arrivals[-1][2], 'test' if plugin.name == 'probes' else None)

    def test_invalid_import_fails_at_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'rules.yml')
            cases = [(None, []), ('[', []), ('rules: []', []), ('- invalid-origin', []),
                     ("- '*'", ['https://api.example.org']), ('[]', 'invalid')]
            for content, inline in cases:
                with self.subTest(content=content, inline=inline):
                    if content is not None:
                        path.write_text(content)
                    plugin = CovenantHttpPlugin('invalid-import')
                    cfg = {'import_credential_targets': path.name, 'credential_targets': inline}
                    plugin.config = {'allowed_targets': ['*'], 'covenant': {'config_dir': directory},
                                     'probes': [{'name': 'health', 'config': cfg, 'collects': []}]}
                    with self.assertRaises(CovenantConfigurationError):
                        plugin.safe_init()

    def test_fixed_target_can_disable_environment_proxy_and_netrc(self):
        plugin = CovenantHttpPlugin('fixed-target')
        with tempfile.TemporaryDirectory() as directory, upstream() as (_, url, direct), \
                upstream() as (_, proxy, forwarded):
            netrc = Path(directory, '.netrc')
            netrc.write_text('machine 127.0.0.1 login probe password example\n')
            netrc.chmod(0o600)
            with patch.dict(os.environ, {'NETRC': str(netrc), 'http_proxy': proxy}, clear=True):
                for options in ({}, {'trust_env': True}, {'trust_env': False},
                                {'credential_targets': []}):
                    target = CovenantTarget('health', dict(options, url=url), [], plugin.registry)
                    plugin.targets = [target]
                    req = CovenantEPTObject('test', 'test:1', 'test', 'probes', {}, {}, lambda obj: None)
                    plugin.do_probes(req)
            self.assertEqual(len(forwarded), 2)
            self.assertTrue(all(auth for _, auth, _ in forwarded))
            self.assertEqual(direct, [('/', None, None), ('/', None, None)])

    def test_invalid_trust_env_rejected_at_startup(self):
        for options in ({'trust_env': True}, {'url': 'http://fixed.test', 'trust_env': 'false'},
                        {'url': 'http://fixed.test', 'trust_env': True, 'credential_targets': []}):
            plugin = CovenantHttpPlugin('invalid-environment')
            plugin.config = {'allowed_targets': ['*'], 'probes': [{'name': 'health', 'config': options, 'collects': []}]}
            with self.subTest(options=options), patch('covenant.classes.plugins.EPTS_SYNC'), \
                    self.assertRaises(CovenantConfigurationError):
                plugin.safe_init()

    def test_connection_error_logs_target_name_without_query_secret(self):
        plugin = CovenantHttpPlugin('connection-check')
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            url = 'http://127.0.0.1:%d/health?token=private-marker' % reserved.getsockname()[1]
            for config in ({'url': url, 'trust_env': False}, {}):
                plugin.targets = [CovenantTarget('health', config, [], plugin.registry)]
                req = CovenantEPTObject('test', 'test:1', 'test', 'probes',
                                        {'target': url}, {}, lambda obj: None)
                with self.assertLogs('covenant', level='DEBUG') as logs:
                    plugin.do_probes(req)
                output = '\n'.join(logs.output)
                self.assertIn('health', output)
                self.assertIn('ConnectionError', output)
                self.assertNotIn('private-marker', output)
                self.assertNotIn('Traceback', output)

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
