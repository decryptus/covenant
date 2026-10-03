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
from covenant.plugins import certlord
from runtime_smoke import ReadyServer, READY, ERRORS, ADDRESS, serve, CONFIG_DIR
from test_certlord import FULL, EMPTY


class Source(BaseHTTPRequestHandler):
    status = 200
    body = FULL.encode()
    calls = 0

    def do_GET(self):
        type(self).calls += 1
        if self.path != '/api/certificates/metrics' or self.headers.get('Authorization') != 'Bearer synthetic-reader':
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
        conf['endpoints'] = {'certificates': {'plugin': 'certlord', 'metrics': [{
            'name': 'certlord', 'config': {
                'url': 'http://127.0.0.1:%s/api/certificates/metrics' % source.server_port,
                'token_file': 'reader.token', 'timeout': 1}, 'collects': []}]}}
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
            response = requests.get(url, timeout=4)
            assert response.status_code == 200 and 'source_up 1' in response.text, response.text
            assert 'certlord_certificate_not_after' in response.text
            Source.status = 503
            response = requests.get(url, timeout=4)
            assert response.status_code == 200 and 'source_up 0' in response.text
            assert 'certlord_certificate_not_after' not in response.text
            Source.status, Source.body = 200, EMPTY.encode()
            response = requests.get(url, timeout=4)
            assert 'source_up 1' in response.text and 'certificates_observed 0.0' in response.text
            assert Source.calls == 3
            print('CertLord runtime integration OK')
        finally:
            os.kill(os.getpid(), signal.SIGTERM)
            server.join(3)
            source.shutdown()
            source.server_close()
            thread.join(3)
            assert not server.is_alive()


if __name__ == '__main__':
    main()
