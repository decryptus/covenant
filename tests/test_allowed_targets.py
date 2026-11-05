"""Caller-selected destinations are checked before opening network connections."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import yaml

from covenant.classes import config
from covenant.classes.exceptions import CovenantConfigurationError, CovenantTargetFailed
from covenant.plugins.http import CovenantHttpPlugin
from covenant.plugins.pfilestat import CovenantFilestatPlugin
from covenant.plugins.predis import CovenantRedisPlugin
from covenant.plugins.pssl import CovenantSslPlugin
from test_credential_targets import upstream
from test_redis_credentials import redis_peer
from test_templates import request


def endpoint(plugin_type, rules, **options):
    plugin = plugin_type('limited')
    plugin.config = {'allowed_targets': rules, 'probes': [
        {'name': 'status', 'config': {}, 'collects': []}]}
    plugin.config.update(options)
    with patch('covenant.classes.plugins.EPTS_SYNC'):
        plugin.safe_init()
    return plugin


class AllowedTargetTests(unittest.TestCase):
    def test_http_rechecks_redirect_and_rejects_before_connect(self):
        with upstream() as (server, first, hits), upstream() as (_, second, denied):
            plugin = endpoint(CovenantHttpPlugin, [first])
            plugin.do_probes(request(first))
            self.assertEqual(len(hits), 1)
            server.location = second
            with self.assertLogs('covenant.plugins.http'):
                plugin.do_probes(request(first))
                plugin.do_probes(request(second))
            self.assertEqual(len(hits), 2)
            self.assertEqual(denied, [])

    def test_exclusion_blocks_http_redirect_even_when_wildcard_allows_it(self):
        with upstream() as (server, first, hits), upstream() as (_, second, denied):
            plugin = endpoint(CovenantHttpPlugin, ['*'], disallowed_targets=[second])
            server.location = second
            with self.assertLogs('covenant.plugins.http'):
                plugin.do_probes(request(first))
            self.assertEqual(len(hits), 1)
            self.assertEqual(denied, [])

    def test_policy_imports_at_config_load(self):
        from types import SimpleNamespace
        rule = {'scheme': 'tls', 'port': 443, 'regex': r'node[0-9]+[.]example[.]net'}
        with tempfile.TemporaryDirectory() as folder, patch.object(config.signal, 'signal'), \
                patch.object(config, 'init_modules'), patch.dict(config.ENDPOINTS, clear=True), \
                patch.object(config, 'DWHO_THREADS', []), patch('covenant.classes.plugins.EPTS_SYNC'):
            root = Path(folder)
            path = root / 'covenant.yml'

            def load(**options):
                probe = {'plugin': 'ssl', 'probes': [{'name': 'status', 'collects': []}]}
                probe.update(options)
                path.write_text(yaml.safe_dump({'general': {}, 'endpoints': {'policy': probe}}))
                config.load_conf(str(path), SimpleNamespace())
                return config.ENDPOINTS['policy'].allowed_targets

            (root / 'allowed.yml').write_text(yaml.safe_dump([rule]))
            (root / 'blocked.yml').write_text(yaml.safe_dump([dict(rule, regex=r'node1[.]example[.]net')]))
            (root / 'empty.yml').write_text('[]')
            policy = load(import_allowed_targets='allowed.yml', allowed_targets=['tls://extra'],
                          import_disallowed_targets='blocked.yml', disallowed_targets=['tls://node2.example.net'])
            for host, expected in [('node3.example.net', True), ('extra', True), ('node1.example.net', False),
                                   ('node2.example.net', False), ('other', False), ('node3.example.net.evil', False)]:
                self.assertEqual(policy.allows('tls://' + host), expected, host)
            policy = load(import_disallowed_targets='blocked.yml')
            self.assertTrue(policy.allows('tls://other'))
            self.assertFalse(policy.allows('tls://node1.example.net'))
            self.assertFalse(load(import_allowed_targets='empty.yml').allows('tls://other'))
            self.assertTrue(load(import_disallowed_targets='empty.yml').allows('tls://other'))
            for key in ('import_allowed_targets', 'import_disallowed_targets'):
                for content in (None, '{}', '[', yaml.safe_dump([dict(rule, regex='[')])):
                    if content is not None:
                        (root / 'bad.yml').write_text(content)
                    with self.subTest(key=key, content=content), self.assertRaises(CovenantConfigurationError):
                        load(**{key: 'missing.yml' if content is None else 'bad.yml'})

    def test_example_wildcard_and_regex_exclusion(self):
        from covenant.services.credential_targets import EndpointTargets, TlsTargetOrigins, load_origin_rules
        directory = Path(__file__).resolve().parents[1] / 'etc' / 'covenant'
        rules = {}
        for key, filename in [('allowed_targets', 'tls-allowed.yml'), ('disallowed_targets', 'tls-disallowed.yml')]:
            rules[key] = load_origin_rules({'import_' + key: 'rules/' + filename}, key, str(directory))
        policy = EndpointTargets(TlsTargetOrigins, rules)
        self.assertTrue(policy.allows('tls://api.example.net:443'))
        self.assertFalse(policy.allows('tls://node12.example.net:443'))
        self.assertFalse(policy.allows('tls://internal.api.example.net:443'))
        self.assertFalse(policy.allows('tls://api.example.net:8443'))

    def test_fixed_http_origin_wins_over_the_requested_target(self):
        with upstream() as (_, fixed, hits), upstream() as (_, other, denied):
            plugin = endpoint(CovenantHttpPlugin, [])
            target = Mock(config={'url': fixed, 'trust_env': False}, credentials=None)
            plugin._do_call(request(other), targets=[target])
            self.assertEqual(len(hits), 1)
            self.assertEqual(denied, [])

    def test_misplaced_allowlist_is_rejected(self):
        for cfg in ({'vars': {'allowed_targets': []}},
                    {'metrics': [{'config': {'allowed_targets': []}}]}):
            plugin = CovenantHttpPlugin('misplaced')
            plugin.config = cfg
            with self.assertRaisesRegex(CovenantConfigurationError, 'on the endpoint'):
                plugin.safe_init()

    def test_redis_checks_destination_independently_from_credentials(self):
        with redis_peer() as (url, commands):
            plugin = endpoint(CovenantRedisPlugin, [url])
            target = Mock(config={'protocol': 2}, credentials={'username': 'u', 'password': 'p'})
            plugin._do_call(request(url), targets=[target])
            self.assertTrue(any(cmd[0].upper() == b'INFO' for cmd in commands))
            self.assertFalse(any(cmd[0].upper() == b'AUTH' for cmd in commands))
            denied = endpoint(CovenantRedisPlugin, [])
            with patch('covenant.plugins.predis.redis.from_url') as connect:
                target = Mock(config={'credential_targets': ['*']}, credentials=None)
                denied._do_call(request(url), targets=[target])
                connect.assert_not_called()
                self.assertIsInstance(target.call_args[0][0], CovenantTargetFailed)

    def test_ssl_uses_socket_destination_even_with_an_allowed_common_name(self):
        plugin = endpoint(CovenantSslPlugin, ['tls://good.example:443'])
        with patch.object(plugin, '_connect', side_effect=OSError('test')) as connect:
            for url in ('https://127.0.0.1', 'https://good.example:8443'):
                target = Mock(config={'common_name': 'good.example'})
                plugin._do_call(request(url), targets=[target])
                connect.assert_not_called()
                self.assertIsInstance(target.call_args[0][0], CovenantTargetFailed)
            plugin._do_call(request('https://good.example'), targets=[Mock(config={})])
            self.assertEqual(connect.call_args.args[1:3], ('good.example', 443))

    def test_loader_passes_endpoint_policy_and_fails_closed_on_invalid_rules(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder, patch.object(config.signal, 'signal'), \
                patch.object(config, 'init_modules'), patch.dict(config.ENDPOINTS, clear=True), \
                patch.object(config, 'DWHO_THREADS', []), patch('covenant.classes.plugins.EPTS_SYNC'):
            path = Path(folder, 'covenant.yml')
            path.write_text(yaml.safe_dump({'general': {}, 'endpoints': {'tls-test': {
                'plugin': 'ssl', 'allowed_targets': [], 'probes': [
                    {'name': 'status', 'config': {}, 'collects': []}]}}}))
            config.load_conf(str(path), SimpleNamespace())
            self.assertFalse(config.ENDPOINTS['tls-test'].allowed_targets.allows('tls://example.com'))
        for rules in (None, 'tls://host', ['https://host'], ['tls://host:0']):
            with self.subTest(rules=rules), self.assertRaises(CovenantConfigurationError):
                endpoint(CovenantSslPlugin, rules)
        with self.assertRaises(CovenantConfigurationError):
            endpoint(CovenantFilestatPlugin, [])
