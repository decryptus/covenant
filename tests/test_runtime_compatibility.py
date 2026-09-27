# -*- coding: utf-8 -*-
"""Keep the runtime's process-global registries/signals isolated per scenario."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from covenant.classes.config import load_conf
from covenant.classes.exceptions import CovenantConfigurationError

SMOKE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'runtime_smoke.py')


class RuntimeCompatibilityTests(unittest.TestCase):
    def run_runtime(self, mode):
        result = subprocess.run([sys.executable, SMOKE_SCRIPT, mode],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('runtime compatibility OK: ' + mode, result.stdout)

    def test_legacy_yaml_without_result_timeout(self):
        self.run_runtime('legacy')

    def test_configured_deadline_is_http_504_on_both_routes(self):
        self.run_runtime('bounded')

    def test_invalid_deadline_rejected_before_module_initialization(self):
        for value in (None, False, 0, -1, float('nan'), float('inf')):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, 'covenant.yml')
                with open(path, 'w') as stream:
                    yaml.safe_dump({'general': {'result_timeout': value}}, stream)
                with patch('covenant.classes.config.signal.signal'), \
                     patch('covenant.classes.config.init_modules') as init_modules:
                    with self.assertRaisesRegex(CovenantConfigurationError, 'result_timeout'):
                        load_conf(path)
                    init_modules.assert_not_called()
