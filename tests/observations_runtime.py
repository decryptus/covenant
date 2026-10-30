"""Isolated real YAML -> Covenant worker -> HTTP source -> HTTPdis scrape."""
import os
import signal
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import requests
import yaml
from dwho.config import DWHO_THREADS, set_softname, set_softver
from httpdis import httpdis
from covenant.classes.config import load_conf, start_endpoints
from covenant.plugins import observations
from runtime_smoke import ReadyServer, READY, ERRORS, ADDRESS, serve, CONFIG_DIR
from test_observations import payload
import json


class Source(BaseHTTPRequestHandler):
    status = 200
    body = json.dumps(payload('certlord')).encode()
    calls = 0

    def do_GET(self):
        type(self).calls += 1
        if self.path != '/observations' or self.headers.get('Authorization') != 'Bearer synthetic-reader':
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(self.status)
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


def main():
    set_softname('covenant')
    set_softver('0.0.69')
    source = ThreadingHTTPServer(('127.0.0.1', 0), Source)
    thread = threading.Thread(target=source.serve_forever, daemon=True)
    thread.start()
    with tempfile.TemporaryDirectory() as directory:
        with open(os.path.join(CONFIG_DIR, 'covenant.yml.example')) as stream:
            conf = yaml.safe_load(stream)
        conf.pop('import_modules', None)
        conf['general'].update(listen_addr='127.0.0.1', listen_port=0)
        conf['modules'] = {}
        for name in ('metrics', 'probes'):
            with open(os.path.join(CONFIG_DIR, 'modules', name + '.yml')) as stream:
                conf['modules'].update(yaml.safe_load(stream))
        with open(os.path.join(directory, 'reader.token'), 'w') as stream:
            stream.write('synthetic-reader')
        conf['endpoints'] = {'certificates': {'plugin': 'certlord_observation', 'metrics': [{
            'name': 'certlord', 'config': {
                'url': 'http://127.0.0.1:%s/observations' % source.server_port,
                'token_file': 'reader.token', 'timeout': 1}, 'collects': []}]}}
        conf['endpoints']['monit'] = dict(conf['endpoints']['certificates'], plugin='monit_observation')
        path = os.path.join(directory, 'covenant.yml')
        with open(path, 'w') as stream:
            yaml.safe_dump(conf, stream)
        options = load_conf(path, SimpleNamespace())
        httpdis.init(options, False)
        start_endpoints()
        DWHO_THREADS.append(httpdis.stop)
        server = threading.Thread(target=serve, args=(options,), daemon=True)
        server.start()
        try:
            assert READY.wait(3) and not ERRORS, ERRORS
            url = 'http://%s:%s/metrics/certificates' % ADDRESS[0]
            for kind, endpoint in (('certlord','certificates'),('monit','monit')):
                url = 'http://%s:%s/metrics/%s' % (*ADDRESS[0], endpoint)
                Source.status, Source.body = 200, json.dumps(payload(kind)).encode()
                response = requests.get(url, timeout=4)
                assert response.status_code == 200 and '_observation_up 1' in response.text, response.text
                assert '_observation_manifest' in response.text
                Source.status = 503
                response = requests.get(url, timeout=4)
                assert '_observation_up 0' in response.text and '_observation_value' not in response.text
                Source.status = 200
                response = requests.get(url, timeout=4)
                assert '_observation_up 1' in response.text
            assert Source.calls == 6
            print('Complete observations runtime integration OK')
        finally:
            os.kill(os.getpid(), signal.SIGTERM)
            server.join(3)
            source.shutdown()
            source.server_close()
            thread.join(3)
            assert not server.is_alive()


if __name__ == '__main__':
    main()
