# -*- coding: utf-8 -*-
# Copyright (C) 2026 Adrien Delle Cave
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only, fixed-destination CertLord collector."""
import sys

# Keep legacy Python installations able to load the other plugins.
if sys.version_info >= (3, 8):
    import ipaddress
    import math
    import os
    import re
    import time
    from urllib.parse import urlsplit

    import requests

    from covenant.classes.exceptions import CovenantConfigurationError
    from covenant.classes.plugins import CovenantPlugBase, PLUGINS
    from covenant.services.certlord import MAX_BYTES, snapshot_metrics

    CONFIG_KEYS = frozenset(('url', 'timeout', 'token_file', 'ca_file'))
    TOKEN_PATTERN = re.compile(r'[A-Za-z0-9._~+/-]+=*\Z')
    UP = b'# HELP covenant_certlord_source_up Whether the complete CertLord snapshot was collected.\n# TYPE covenant_certlord_source_up gauge\n'


    class CovenantCertlordPlugin(CovenantPlugBase):
        PLUGIN_NAME = 'certlord'

        def safe_init(self):
            super().safe_init()
            if self.type != 'metric' or len(self.targets) != 1:
                raise CovenantConfigurationError('CertLord requires exactly one metrics target')
            cfg = self.targets[0].config
            if set(cfg) - CONFIG_KEYS or self.targets[0].credentials or self.targets[0].collects:
                raise CovenantConfigurationError('Unsupported CertLord target configuration')
            url = cfg.get('url', '')
            parsed = urlsplit(url)
            loopback = False
            try:
                loopback = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                pass
            if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or any(char.isspace() for char in url)
                    or (parsed.scheme == 'http' and not loopback)):
                raise CovenantConfigurationError('Use HTTPS or an explicit loopback IP for CertLord')
            timeout = cfg.get('timeout', 10)
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
                raise CovenantConfigurationError('CertLord timeout must be positive and finite')
            if timeout * 2 >= self.config['general']['result_timeout']:
                raise CovenantConfigurationError('CertLord result_timeout must exceed twice its network timeout')
            self._url = url
            self._timeout = timeout
            directory = self.config['covenant']['config_dir']
            self._token_file = self._path(cfg.get('token_file'), directory)
            self._verify = self._path(cfg.get('ca_file'), directory) or True
            if not loopback and not self._token_file:
                raise CovenantConfigurationError('Remote CertLord collection requires a read token file')

        @staticmethod
        def _path(value, directory):
            if value is None:
                return None
            if not isinstance(value, str) or not value:
                raise CovenantConfigurationError('Expected a credential or CA file path')
            return os.path.join(directory, value)

        def _do_call(self, obj, targets = None, registry = None):
            # Neither query parameters nor dynamic target copies can choose the origin.
            if obj.get_params().get('target'):
                raise CovenantConfigurationError('CertLord does not accept dynamic targets')
            try:
                headers = {'Accept': 'text/plain'}
                if self._token_file:
                    with open(self._token_file, encoding='ascii') as stream:
                        token = stream.read(8193).strip()
                    if not token or len(token) > 8192 or not TOKEN_PATTERN.fullmatch(token):
                        raise ValueError('Invalid token file')
                    headers['Authorization'] = 'Bearer ' + token
                started = time.monotonic()
                with requests.Session() as session:
                    # Do not inherit netrc credentials or proxy settings for a privileged read.
                    session.trust_env = False
                    with session.get(self._url, headers=headers, timeout=self._timeout,
                                     verify=self._verify, allow_redirects=False, stream=True) as response:
                        if response.status_code != 200:
                            raise ValueError('Collection failed')
                        chunks = []
                        size = 0
                        for chunk in response.iter_content(16384):
                            size += len(chunk)
                            if size > MAX_BYTES or time.monotonic() - started > self._timeout:
                                raise ValueError('Collection limit exceeded')
                            chunks.append(chunk)
                        output = snapshot_metrics(b''.join(chunks).decode('utf-8'))
                return UP + b'covenant_certlord_source_up 1\n' + output
            except Exception:
                # No raw URL, response body, token or exception text in output/logs.
                # A fresh failure snapshot contains no previously healthy certificate gauges.
                return UP + b'covenant_certlord_source_up 0\n'


    PLUGINS.register(CovenantCertlordPlugin)
