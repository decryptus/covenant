"""Exercise the packaged or source CLI with real process identities on Linux."""
import grp
import importlib.util
import os
from pathlib import Path
import pwd
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'bin' / 'covenant'
if not CLI.is_file():
    CLI = shutil.which('covenant')


@unittest.skipUnless(sys.platform.startswith('linux') and importlib.util.find_spec('pyjq'),
                     'full Linux CLI dependencies required (exercised in the Docker image)')
class DaemonStartupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.root.chmod(0o755)
        self.env = os.environ.copy()
        for name in ('COVENANT_USER', 'COVENANT_GROUP'):
            self.env.pop(name, None)
        if os.geteuid() == 0:
            try:
                self.user = pwd.getpwnam('covenant')
                self.gid = grp.getgrnam('covenant').gr_gid
            except KeyError:
                if not (ROOT / 'bin' / 'covenant').is_file():
                    raise
                self.user = pwd.getpwnam('nobody')
                self.gid = self.user.pw_gid
                self.env.update(COVENANT_USER=self.user.pw_name,
                                COVENANT_GROUP=grp.getgrgid(self.gid).gr_name)
        else:
            self.user = pwd.getpwuid(os.geteuid())
            self.gid = os.getegid()
        runtime = self.root / 'runtime'
        runtime.mkdir()
        os.chown(runtime, self.user.pw_uid, self.gid)
        self.pidfile = runtime / 'covenant.pid'
        self.sock = socket.socket()
        self.addCleanup(self.sock.close)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(1)
        config = {'general': {'listen_addr': '127.0.0.1', 'listen_port': self.sock.getsockname()[1]},
                  'endpoints': {'file': {'plugin': 'filestat', 'probes': [
                      {'name': 'file', 'config': {'path': '/tmp'}, 'collects': []}]}}}
        path = self.root / 'covenant.yml'
        path.write_text(yaml.safe_dump(config))
        self.command = [sys.executable, str(CLI), '-p', str(self.pidfile),
                        '--logfile', str(runtime / 'daemon.log'), '-c', str(path)]

    def launch(self, *args, **kwargs):
        return subprocess.run(self.command + list(args), env=self.env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=12, **kwargs)

    def test_unknown_configured_identity_stops_before_pid_creation(self):
        for option, variable in (('-u', 'COVENANT_USER'), ('-g', 'COVENANT_GROUP')):
            with self.subTest(option=option):
                original = self.env.copy()
                self.env[variable] = 'covenant-nonexistent-test'
                result = self.launch()
                self.env = original
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'unknown service', result.stdout)
                self.assertFalse(self.pidfile.exists())
                result = self.launch(option, 'covenant-nonexistent-test')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'unknown service', result.stdout)

    def test_bind_failure_reaches_both_launchers_and_cleans_pid(self):
        for mode in (['-f'], []):
            with self.subTest(mode=mode):
                result = self.launch(*mode)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('Address already in use', (self.pidfile.parent / 'daemon.log').read_text())
                self.assertFalse(self.pidfile.exists())

    def test_detached_listener_runs_with_expected_identity(self):
        address = self.sock.getsockname()
        self.sock.close()
        identities = {}
        if os.geteuid() == 0:
            identities['preexec_fn'] = lambda: os.setgroups([0])
        result = self.launch(**identities)
        self.assertEqual(result.returncode, 0, result.stdout)
        pid = int(self.pidfile.read_text())
        try:
            requests.get('http://%s:%d/server' % address, timeout=2)
            status = dict(line.split(':', 1) for line in Path('/proc/%d/status' % pid).read_text().splitlines())
            self.assertEqual(set(map(int, status['Uid'].split())), {self.user.pw_uid})
            self.assertEqual(set(map(int, status['Gid'].split())), {self.gid})
            expected = (os.getgrouplist(self.user.pw_name, self.gid)
                        if os.geteuid() == 0 else os.getgroups())
            self.assertEqual(set(map(int, status['Groups'].split())), set(expected))
        finally:
            os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if not self.pidfile.exists():
                break
            time.sleep(0.05)
        self.assertFalse(self.pidfile.exists())
