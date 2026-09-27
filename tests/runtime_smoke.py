# -*- coding: utf-8 -*-
"""Isolated runtime probe: real YAML, plugins, HTTPdis socket and SIGTERM hook."""

import os
import shutil
import signal
import sys
import tempfile
import threading
from types import SimpleNamespace

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
        conf['general'].update(listen_addr='127.0.0.1', listen_port=0)
        conf['general'].pop('result_timeout', None)
        if sys.argv[1] == 'bounded':
            conf['general']['result_timeout'] = 0.05
        conf['endpoints'] = {
            'files': {'plugin': 'filestat', 'import_metrics': 'probes.d/file.yml'},
            'file-probe': {'plugin': 'filestat', 'import_probes': 'probes.d/file.yml'},
        }
        config_path = os.path.join(directory, 'covenant.yml')
        with open(config_path, 'w') as stream:
            yaml.safe_dump(conf, stream)
        options = load_conf(config_path, SimpleNamespace())
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
            base = 'http://%s:%s' % ADDRESS[0]
            for route in ('metrics/files', 'probe/file-probe', 'probes/file-probe'):
                response = requests.get(base + '/' + route, params={'target': config_path}, timeout=3)
                assert response.status_code == 200, (route, response.status_code, response.text)
                assert b'file_exists 1.0\n' in response.content, response.content
                assert 'text/plain' in response.headers['Content-Type']
            response = requests.get(base + '/server', timeout=3)
            assert response.status_code == 200, response.text
            assert b'version_info{' in response.content, response.content
            for route, status in (('metrics/missing', 404), ('metrics/file-probe', 400),
                                   ('probe/files', 400)):
                response = requests.get(base + '/' + route, timeout=3)
                assert response.status_code == status, (route, response.status_code, response.text)
            def fail(obj):
                obj.add_error('plugin failure')
                obj()
            EPTS_SYNC['files'].qput = fail
            assert requests.get(base + '/metrics/files', timeout=3).status_code == 500
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
