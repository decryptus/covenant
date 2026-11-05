# -*- coding: utf-8 -*-
"""Isolated runtime probe: real YAML, plugins, HTTPdis socket and SIGTERM hook."""

import os
import re
import shutil
import signal
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

import requests
import yaml
from dwho.config import DWHO_THREADS, set_softname, set_softver
from httpdis import httpdis

from covenant.classes.config import load_conf, start_endpoints
from covenant.classes.plugins import ENDPOINTS, EPTS_SYNC
from covenant.filters import fjmespath
from covenant.modules import metrics, probes
from covenant.plugins import pfilestat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, 'etc', 'covenant')
READY = threading.Event()
ADDRESS = []
ERRORS = []


class ReadyServer(httpdis.KillableThreadingHTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ADDRESS.append(self.server_address)
        READY.set()


def serve(options):
    try:
        httpdis.run(options, http_server_class=ReadyServer)
    except BaseException as error:
        ERRORS.append(error)
        READY.set()


def main():
    set_softname('covenant')
    set_softver('0.0.69')
    with tempfile.TemporaryDirectory() as directory:
        shutil.copytree(os.path.join(CONFIG_DIR, 'modules'), os.path.join(directory, 'modules'))
        shutil.copytree(os.path.join(CONFIG_DIR, 'probes.d'), os.path.join(directory, 'probes.d'))
        with open(os.path.join(CONFIG_DIR, 'covenant.yml.example')) as stream:
            conf = yaml.safe_load(stream)
        assert conf['general']['listen_addr'] == '127.0.0.1'
        conf['general']['listen_port'] = 0
        if sys.argv[1] == 'legacy':
            del conf['general']['listen_addr']
        elif sys.argv[1] == 'override':
            conf['general']['listen_addr'] = '0.0.0.0'
        conf['general'].pop('result_timeout', None)
        if sys.argv[1] == 'bounded':
            conf['general']['listen_addr'] = None
            conf['general']['result_timeout'] = 0.05
        config_path = os.path.join(directory, 'covenant.yml')
        shared_rule = '^' + re.escape(config_path) + '$'
        local_path = os.path.join(directory, 'local')
        denied_path = os.path.join(directory, 'denied')
        for path in (local_path, denied_path):
            with open(path, 'w'):
                pass
        for name, rules in (('shared.yml', [shared_rule]), ('denied.yml', ['^' + re.escape(denied_path) + '$'])):
            with open(os.path.join(directory, name), 'w') as stream:
                yaml.safe_dump(rules, stream)
        file_endpoint = {'plugin': 'filestat', 'import_state_include_paths': 'shared.yml',
                         'import_state_exclude_paths': 'denied.yml'}
        conf['endpoints'] = {
            'files': dict(file_endpoint, import_metrics='probes.d/file.yml'),
            'file-probe': dict(file_endpoint, import_probes='probes.d/file.yml',
                               vars={'state_include_paths': '^' + re.escape(directory) + '/'}),
        }
        with open(config_path, 'w') as stream:
            yaml.safe_dump(conf, stream)
        cli = SimpleNamespace(listen_addr='127.0.0.1') if sys.argv[1] == 'override' else SimpleNamespace()
        options = load_conf(config_path, cli)
        if sys.argv[1] == 'override':
            assert options.configuration['general']['listen_addr'] == '0.0.0.0'
        assert options.configuration['_config_directory'] == directory
        if sys.argv[1] != 'bounded':
            assert options.configuration['general']['result_timeout'] == 30
        httpdis.init(options, False)
        start_endpoints()
        assert all(endpoint.is_alive() for endpoint in ENDPOINTS.values())
        thread = threading.Thread(target=serve, args=(options,), daemon=True)
        DWHO_THREADS.append(httpdis.stop)
        stopped = []
        DWHO_THREADS.append(lambda: stopped.append(True))
        thread.start()
        try:
            assert READY.wait(3), 'server did not start'
            assert not ERRORS, ERRORS
            assert ADDRESS[0][0] == '127.0.0.1', ADDRESS[0]
            base = 'http://%s:%s' % ADDRESS[0]
            for route in ('metrics/files', 'probe/file-probe', 'probes/file-probe'):
                response = requests.get(base + '/' + route, params={'target': config_path}, timeout=3)
                assert response.status_code == 200, (route, response.status_code, response.text)
                assert b'file_exists 1.0\n' in response.content, response.content
                assert 'text/plain' in response.headers['Content-Type']
            outside_link = os.path.join(directory, 'outside-link')
            os.symlink(os.path.abspath(__file__), outside_link)
            for target, value in ((outside_link, 0), (config_path, 1)):
                response = requests.get(base + '/probe/file-probe', params={'target': target}, timeout=3)
                assert response.status_code == 200, response.text
                assert ('file_exists %d.0\n' % value).encode() in response.content, response.text
            for route, path, expected in (('metrics/files', local_path, 0),
                                          ('probe/file-probe', local_path, 1),
                                          ('probe/file-probe', denied_path, 0)):
                response = requests.get(base + '/' + route, params={'target': path}, timeout=3)
                assert response.status_code == 200, response.text
                assert ('file_exists %d.0\n' % expected).encode() in response.content, response.text
            response = requests.get(base + '/server', timeout=3)
            assert response.status_code == 200, response.text
            assert b'version_info{' in response.content, response.content
            for route, status in (('metrics/missing', 404), ('metrics/file-probe', 400),
                                   ('probe/files', 400)):
                response = requests.get(base + '/' + route, timeout=3)
                assert response.status_code == status, (route, response.status_code, response.text)
            for route, owner, method in (
                    ('metrics/files', metrics.MetricsModule, '_push_epts_sync'),
                    ('probe/file-probe', probes.ProbesModule, '_push_epts_sync'),
                    ('server', metrics, 'generate_latest')):
                with patch.object(owner, method, side_effect=RuntimeError('private exception detail')):
                    response = requests.get(base + '/' + route, timeout=3)
                    assert response.status_code == 500, (route, response.status_code)
                    assert 'private exception detail' not in response.text
                response = requests.get(base + '/' + route, params={'target': config_path}, timeout=3)
                assert response.status_code == 200, (route, response.status_code)

            def fail(obj):
                obj.add_error('private plugin detail')
                obj()

            for endpoint, route in (('files', 'metrics/files'), ('file-probe', 'probes/file-probe')):
                with patch.object(EPTS_SYNC[endpoint], 'qput', fail):
                    response = requests.get(base + '/' + route, timeout=3)
                    assert response.status_code == 500, (route, response.status_code)
                    assert 'private plugin detail' not in response.text
                response = requests.get(base + '/' + route, params={'unknown': 'invalid'}, timeout=3)
                assert response.status_code == 400, (route, response.status_code)
            if sys.argv[1] == 'bounded':
                for endpoint, route in (('files', 'metrics/files'), ('file-probe', 'probe/file-probe')):
                    EPTS_SYNC[endpoint].qput = lambda obj: None
                    response = requests.get(base + '/' + route, timeout=3)
                    assert response.status_code == 504, (route, response.status_code, response.text)
                assert requests.get(base + '/server', timeout=3).status_code == 200
        finally:
            os.kill(os.getpid(), signal.SIGTERM)
            thread.join(timeout=3)
        assert stopped, 'DWho stop hooks were not called'
        assert not thread.is_alive(), 'HTTP server did not stop'
        assert not ERRORS, ERRORS
        print('runtime compatibility OK: ' + sys.argv[1])


if __name__ == '__main__':
    main()
