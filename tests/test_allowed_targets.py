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


_OMITTED = object()


def endpoint(plugin_type, rules=_OMITTED, **options):
    plugin = plugin_type('limited')
    plugin.config = {'probes': [
        {'name': 'status', 'config': {}, 'collects': []}]}
    plugin.config.update(options)
    if rules is not _OMITTED:
        plugin.config['allowed_targets'] = rules
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

    def test_imported_exclusions_block_http_redirects_even_without_an_allowlist(self):
        with tempfile.TemporaryDirectory() as folder, upstream() as (server, first, hits), upstream() as (_, second, denied):
            path = Path(folder, 'exclude.yml')
            path.write_text(yaml.safe_dump([second]))
            plugin = endpoint(CovenantHttpPlugin, import_disallowed_targets=path.name,
                              covenant={'config_dir': folder})
            path.unlink()
            server.location = second
            with self.assertLogs('covenant.plugins.http'):
                plugin.do_probes(request(first))
            self.assertEqual(len(hits), 1)
            self.assertEqual(denied, [])

    def test_imported_and_inline_rules_share_syntax_and_deny_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'allow.yml').write_text(yaml.safe_dump(['tls://*.example.test']))
            Path(folder, 'deny.yml').write_text(yaml.safe_dump([
                {'scheme': 'tls', 'port': 443, 'regex': r'node[0-9]+\.example\.test'}]))
            plugin = endpoint(CovenantSslPlugin, ['tls://local.test'],
                              import_allowed_targets='allow.yml', import_disallowed_targets='deny.yml',
                              disallowed_targets=['tls://old.example.test'], covenant={'config_dir': folder})
            for host, expected in [('one.example.test', True), ('a.b.example.test', False),
                                   ('local.test', True), ('other.test', False),
                                   ('old.example.test', False), ('node12.example.test', False)]:
                self.assertEqual(plugin.allowed_targets.allows('tls://' + host), expected, host)

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
        plugin = endpoint(CovenantSslPlugin, disallowed_targets=['tls://*.example.test'])
        for host in ('NODE.EXAMPLE.TEST.', 'node.example.test'):
            with patch.object(plugin, '_connect') as connect:
                plugin._do_call(request('https://' + host), targets=[Mock(config={})])
                connect.assert_not_called()
        self.assertTrue(plugin.allowed_targets.allows('tls://node.example.test:8443'))

    def test_empty_and_invalid_imports(self):
        with tempfile.TemporaryDirectory() as folder:
            loc = {'config_dir': folder}
            path = Path(folder, 'rules.yml')
            for key in ('import_allowed_targets', 'import_disallowed_targets'):
                for content in (None, '', 'rules: []', '[', '- tls://bad:0'):
                    if content is None:
                        if path.exists():
                            path.unlink()
                    else:
                        path.write_text(content)
                    with self.subTest(key=key, data=content), self.assertRaises(CovenantConfigurationError):
                        endpoint(CovenantSslPlugin, covenant=loc, **{key: path.name})
                path.write_text('[]')
                plugin = endpoint(CovenantSslPlugin, covenant=loc, **{key: path.name})
                self.assertEqual(plugin.allowed_targets.allows('tls://any.test'), key == 'import_disallowed_targets')

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
                'plugin': 'ssl', 'import_allowed_targets': 'shared.yml',
                'disallowed_targets': ['tls://excluded.example'], 'probes': [
                    {'name': 'status', 'config': {}, 'collects': []}]}}}))
            Path(folder, 'shared.yml').write_text("- 'tls://*.example'\n")
            config.load_conf(str(path), SimpleNamespace())
            self.assertTrue(config.ENDPOINTS['tls-test'].allowed_targets.allows('tls://ok.example'))
            self.assertFalse(config.ENDPOINTS['tls-test'].allowed_targets.allows('tls://excluded.example'))
            self.assertFalse(config.ENDPOINTS['tls-test'].allowed_targets.allows('tls://example.com'))
        for rules in (None, 'tls://host', ['https://host'], ['tls://host:0']):
            with self.subTest(rules=rules), self.assertRaises(CovenantConfigurationError):
                endpoint(CovenantSslPlugin, rules)
        with self.assertRaises(CovenantConfigurationError):
            endpoint(CovenantFilestatPlugin, [])
