# -*- coding: utf-8 -*-
"""Exercise shipped templates through the real filters and collectors.

HTTP transport is mocked; certificate and filesystem checks are in
test_regressions.py. These tests do not start the HTTP daemon.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

import requests
from mako.template import Template
from prometheus_client import generate_latest
from sonicprobe.helpers import load_yaml

from covenant.classes.exceptions import CovenantTargetFailed
from covenant.classes.plugins import CovenantEPTObject
from covenant.classes.target import CovenantRegistry, CovenantTarget
from covenant.filters import fbuiltins, fjmespath, fregex  # Register filters.
from covenant.plugins.http import CovenantHttpPlugin
from covenant.plugins.pfilestat import CovenantFilestatPlugin


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NGINX_STATUS = ('Active connections: 3\n'
                'server accepts handled requests\n'
                ' 10 10 20 \n'
                'Reading: 1 Writing: 1 Waiting: 1 \n')


def template(path, variables=None):
    with open(os.path.join(ROOT, 'etc', 'covenant', path)) as stream:
        source = stream.read()
    return load_yaml(Template(source, imports=[
        'from os import environ as ENV',
        'from sonicprobe.helpers import to_yaml as my'
    ]).render(vars=variables or {}))


def request(target=None):
    return CovenantEPTObject('test', 'test:1', 'test', 'metrics',
                             {'target': target} if target else {}, {}, lambda obj: None)


class TemplateTests(unittest.TestCase):
    def test_nginx_success_failure_and_recovery(self):
        registry = CovenantRegistry()
        target = CovenantTarget(registry=registry, **template('metrics.d/nginx.yml')[0])
        target(NGINX_STATUS)
        output = generate_latest(registry)
        self.assertIn(b'connections_requests 20.0\n', output)
        self.assertIn(b'connections{state="active"} 3.0\n', output)

        target(CovenantTargetFailed('timeout'))
        output = generate_latest(registry)
        self.assertIn(b'up 0.0\n', output)
        self.assertIn(b'exporter_scrape_failures_total 1.0\n', output)
        self.assertNotIn(b'connections{', output)

        target(NGINX_STATUS)
        output = generate_latest(registry)
        self.assertIn(b'up 1.0\n', output)
        self.assertIn(b'connections_requests 20.0\n', output)
        self.assertIn(b'exporter_scrape_failures_total 1.0\n', output)

    def test_http_timeout_is_forwarded_and_becomes_failure_metrics(self):
        plugin = CovenantHttpPlugin('test-http-timeout')
        config = template('metrics.d/nginx.yml', {
            'url': 'http://configured.invalid', 'timeout': 0.25})[0]
        plugin.targets = [CovenantTarget(registry=plugin.registry, **config)]
        with patch('covenant.plugins.http.requests.get',
                   side_effect=requests.exceptions.Timeout('test timeout')) as get:
            with self.assertLogs('covenant.plugins.http', level='ERROR'):
                output = plugin._fetch(request('http://other.invalid'))
        self.assertEqual(get.call_args[1]['timeout'], 0.25)
        self.assertEqual(get.call_args[1]['url'], 'http://configured.invalid/nginx_status')
        self.assertIn(b'up 0.0\n', output)
        self.assertIn(b'exporter_scrape_failures_total 1.0\n', output)

    def test_shipped_network_templates_have_timeouts(self):
        for filename in ('apache', 'nginx', 'rabbitmq'):
            for target in template('metrics.d/%s.yml' % filename):
                self.assertEqual(target['config']['timeout'], 10)
        for target in template('metrics.d/redis.yml'):
            self.assertEqual(target['config']['socket_timeout'], 10)
            self.assertEqual(target['config']['socket_connect_timeout'], 10)
        for target in template('probes.d/secure-layer.yml'):
            self.assertEqual(target['config']['timeout'], 10)

    def test_file_template_with_allowlist_and_dynamic_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'sshd.pid')
            with open(path, 'w') as stream:
                stream.write('1234\n')
            config = template('probes.d/file.yml', {
                'state_include_paths': ['^' + directory + '/sshd[.]pid$']})[0]
            plugin = CovenantFilestatPlugin('test-file-template')
            plugin.targets = [CovenantTarget(registry=plugin.registry, **config)]
            before = plugin.generate_latest()
            self.assertIn(b'file_exists 1.0\n', plugin._fetch(request(path)))
            os.remove(path)
            self.assertIn(b'file_exists 0.0\n', plugin._fetch(request(path)))
            self.assertEqual(plugin.generate_latest(), before)

    def test_jmespath_final_absence_uses_configured_fallback(self):
        registry = CovenantRegistry()
        target = CovenantTarget('state', {}, [{
            'state': {
                'type': 'gauge', 'documentation': 'State',
                'on_noresult': {'value': 0},
                'value_tasks': [{'@filter': 'jmespath', 'expression': 'state'}]
            }
        }], registry)
        target({'state': 7})
        target({})
        self.assertIn(b'state 0.0\n', generate_latest(registry))


if __name__ == '__main__':
    unittest.main()
