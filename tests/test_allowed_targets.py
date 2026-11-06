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
            with self.assertLogs('covenant.plugins', level='WARNING') as warnings:
                policy = load(import_disallowed_targets='blocked.yml')
            self.assertEqual(len(warnings.records), 1)
            self.assertIn('implicitly allows dynamic', warnings.output[0])
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

    def test_shipped_tls_endpoint_connects_only_to_documented_origin(self):
        directory = Path(__file__).resolve().parents[1] / 'etc' / 'covenant'
        settings = yaml.safe_load((directory / 'covenant.yml.example').read_text())
        probe = settings['endpoints']['secure-layer1']
        plugin = endpoint(CovenantSslPlugin, probe['allowed_targets'])
        with patch.object(plugin, '_connect', side_effect=OSError('test')) as connect:
            for url in ('https://127.0.0.1', 'https://example.com:8443'):
                plugin._do_call(request(url), targets=[Mock(config={})])
                connect.assert_not_called()
            plugin._do_call(request('https://example.com'), targets=[Mock(config={})])
            self.assertEqual(connect.call_args.args[1:3], ('example.com', 443))

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

    def test_redis_exclusion_precedes_connect_and_credential_check(self):
        plugin = endpoint(CovenantRedisPlugin, ['*'], disallowed_targets=[
            {'scheme': 'redis', 'port': 6379, 'cidr': '127.0.0.0/8'}])
        with patch('covenant.plugins.predis.redis.from_url') as connect:
            for host in ('127.0.0.1', '127.1', '2130706433', '[::ffff:127.0.0.1]'):
                target = Mock(config={'credential_targets': ['*']}, credentials=None)
                plugin._do_call(request('redis://' + host), targets=[target])
                self.assertIsInstance(target.call_args[0][0], CovenantTargetFailed)
            connect.assert_not_called()

    def test_deny_only_wildcard_matches_case_and_absolute_dns_name(self):
        plugin = endpoint(CovenantSslPlugin, ['*'], disallowed_targets=['tls://*.example.test'])
        for host in ('NODE.EXAMPLE.TEST.', 'node.example.test'):
            with patch.object(plugin, '_connect') as connect:
                plugin._do_call(request('https://' + host), targets=[Mock(config={})])
                connect.assert_not_called()
        self.assertTrue(plugin.allowed_targets.allows('tls://node.example.test:8443'))

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


class MigrationWarningTests(unittest.TestCase):
    def initialize(self, plugin_type, configs, **options):
        plugin = plugin_type('migration-endpoint')
        plugin.config = {'probes': [
            {'name': 'probe-%d' % index, 'config': cfg, 'collects': []}
            for index, cfg in enumerate(configs)]}
        plugin.config.update(options)
        with patch('covenant.classes.plugins.EPTS_SYNC'):
            plugin.safe_init()
        return plugin

    def test_implicit_dynamic_network_endpoints_warn_once_and_still_collect(self):
        for plugin_type, key, url in (
                (CovenantHttpPlugin, 'url', 'https://example.test'),
                (CovenantRedisPlugin, 'url', 'redis://example.test'),
                (CovenantSslPlugin, 'uri', 'https://example.test')):
            with self.subTest(plugin=plugin_type.PLUGIN_NAME):
                with self.assertLogs('covenant.plugins', level='WARNING') as captured:
                    self.initialize(plugin_type, [{key: url}, {}, {}])
                self.assertEqual(len(captured.records), 1)
                warning = captured.output[0]
                self.assertIn('migration-endpoint', warning)
                self.assertIn('1.0.0 stable', warning)
                self.assertNotIn(url, warning)
        with upstream() as (_, url, calls):
            with self.assertLogs('covenant.plugins', level='WARNING'):
                plugin = self.initialize(CovenantHttpPlugin, [{}])
            plugin.do_probes(request(url))
            self.assertEqual(len(calls), 1)

    def test_fixed_disabled_and_explicit_endpoints_have_no_migration_warning(self):
        with patch('covenant.classes.plugins.LOG.warning') as warning:
            for plugin_type, key in ((CovenantHttpPlugin, 'url'),
                                     (CovenantRedisPlugin, 'url'),
                                     (CovenantSslPlugin, 'uri')):
                fixed = {key: 'https://fixed.test' if key == 'uri' else 'http://fixed.test'}
                self.initialize(plugin_type, [fixed, {'enabled': False}])
                for rules in ([], ['*']):
                    self.initialize(plugin_type, [{}], allowed_targets=rules)
            self.initialize(CovenantFilestatPlugin, [{}])
            warning.assert_not_called()
