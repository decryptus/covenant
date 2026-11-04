"""Verify Redis credential scoping with real loopback RESP commands."""
from contextlib import contextmanager
from pathlib import Path
import socketserver
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from covenant.classes.exceptions import CovenantConfigurationError, CovenantTargetFailed
from covenant.plugins.predis import CovenantRedisPlugin
from covenant.services.credential_targets import RedisCredentialTargets
from test_templates import request, template


@contextmanager
def redis_peer():
    commands = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                args = []
                for _ in range(int(line[1:])):
                    n = int(self.rfile.readline()[1:])
                    args.append(self.rfile.read(n))
                    self.rfile.read(2)
                commands.append(args)
                if args[0].upper() == b'INFO':
                    self.wfile.write(b'$8\r\nuptime:1\r\n')
                else:
                    self.wfile.write(b'+OK\r\n')

    with socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler) as srv:
        srv.daemon_threads = True
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            yield 'redis://127.0.0.1:%d' % srv.server_address[1], commands
        finally:
            srv.shutdown()
            thread.join()


class RedisCredentialTests(unittest.TestCase):
    def collect(self, url, config):
        plugin = CovenantRedisPlugin('redis-policy')
        target = Mock(config=dict(config, protocol=2), credentials={'username': 'review', 'password': 'dummy'})
        plugin.targets = [target]
        plugin._do_call(request(url))
        return target.call_args[0][0]

    def test_credentials_on_the_wire_and_static_precedence(self):
        with redis_peer() as (url, commands), redis_peer() as (other, elsewhere):
            for cfg, authorized in (({}, False), ({'credential_targets': [other]}, False),
                                    ({'credential_targets': [url]}, True),
                                    ({'credential_targets': ['*']}, True)):
                with self.subTest(cfg=cfg):
                    commands.clear()
                    self.assertEqual(self.collect(url, cfg)['uptime'], 1)
                    self.assertEqual([b'AUTH', b'review', b'dummy'] in commands, authorized)
                    if not authorized:
                        self.assertFalse(any(b'dummy' in cmd for cmd in commands))
            self.assertEqual(self.collect(url, {'url': other})['uptime'], 1)
            self.assertIn([b'AUTH', b'review', b'dummy'], elsewhere)

    def test_rejects_caller_connection_options_before_network_io(self):
        for url in ('unix:///tmp/redis.sock', 'redis://user:secret@host/1',
                    'rediss://allowed?ssl_cert_reqs=none', 'redis://allowed?port=9999',
                    'redis://allowed%2eother', 'redis://host:0', 'redis://host/not-a-db'):
            with self.subTest(url=url), patch('covenant.plugins.predis.redis.from_url') as open_conn:
                with self.assertLogs('covenant.plugins.redis'):
                    self.assertIsInstance(self.collect(url, {'credential_targets': ['*']}), CovenantTargetFailed)
                open_conn.assert_not_called()

    def test_tls_material_and_effective_port(self):
        cfg = {'credential_targets': ['rediss://[::1]'], 'ssl_certfile': 'cert',
               'ssl_keyfile': 'key', 'ssl_password': 'pass', 'ssl_ca_certs': 'ca', 'port': 7000}
        for port, authorized in (('', True), (':7000', False)):
            with patch('covenant.plugins.predis.redis.from_url') as open_conn:
                self.collect('rediss://[::1]%s/2' % port, cfg)
                options = open_conn.call_args.kwargs
                self.assertEqual(options['url'], 'rediss://[::1]:%s/2' % (7000 if port else 6379))
                self.assertEqual(options['ssl_ca_certs'], 'ca')
                for key in ('username', 'password', 'ssl_certfile', 'ssl_keyfile', 'ssl_password'):
                    self.assertEqual(key in options, authorized)

    def test_imported_and_inline_redis_template_rules(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'shared.yml').write_text("- 'rediss://*.example.org'\n")
            inline = [{'scheme': 'redis', 'port': 6379, 'cidr': '10.1.0.0/16'},
                      {'scheme': 'rediss', 'port': 6380, 'regex': r'node[0-9]+\.internal'}]
            targets = template('metrics.d/redis.yml', {'import_credential_targets': 'shared.yml',
                                                        'credential_targets': inline})
            with patch('covenant.classes.plugins.EPTS_SYNC'):
                plugin = CovenantRedisPlugin('import')
                # Keep actual template config without loading unrelated metric filters.
                for target in targets:
                    target['collects'] = []
                    target['config']['enabled'] = True
                plugin.config = {'covenant': {'config_dir': d}, 'metrics': targets}
                plugin.safe_init()
            for target in plugin.targets:
                policy = RedisCredentialTargets(target.config['credential_targets'])
                self.assertTrue(policy.allows('rediss://one.example.org'))
                self.assertTrue(policy.allows('redis://10.1.2.3'))
                self.assertTrue(policy.allows('rediss://node42.internal:6380'))
                self.assertFalse(policy.allows('redis://one.example.org'))
            with self.assertRaises(CovenantConfigurationError):
                RedisCredentialTargets(['https://one.example.org'])
