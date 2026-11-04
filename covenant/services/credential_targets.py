"""Destination rules for credentials used by network collectors."""
import os
import re

import six
import yaml
from six.moves.urllib_parse import urlsplit

from covenant.classes.exceptions import CovenantConfigurationError


def _origin(url, ports):
    parts = urlsplit(url)
    if parts.scheme not in ports or not parts.hostname:
        raise ValueError('unsupported scheme or missing host')
    port = parts.port if parts.port is not None else ports[parts.scheme]
    return parts.scheme, parts.hostname.lower(), port


def _rule(value, ports):
    if isinstance(value, six.string_types):
        parts = urlsplit(value)
        scheme, host, port = _origin(value, ports)
        if parts.username is not None or parts.query or parts.fragment or parts.path not in ('', '/'):
            raise ValueError('expected an origin without user information, query or path')
        if host.startswith('*.') and '*' not in host[2:] and len(host) > 2:
            return scheme, port, 'wildcard', host[2:]
        if '*' in host:
            raise ValueError('wildcard must replace the first DNS label')
        return scheme, port, 'host', host

    if not isinstance(value, dict) or set(value) not in (
            {'scheme', 'port', 'regex'}, {'scheme', 'port', 'cidr'}):
        raise ValueError('expected scheme, port and exactly one of regex or cidr')
    scheme, port = value['scheme'], value['port']
    if (scheme not in ports or type(port) is not int or not 1 <= port <= 65535):
        raise ValueError('invalid scheme or port')
    if 'regex' in value:
        if not isinstance(value['regex'], six.string_types) or not value['regex']:
            raise ValueError('expected a nonempty hostname regex')
        pattern = re.compile(value['regex'])
        if hasattr(pattern, 'fullmatch'):
            return scheme, port, 'regex', pattern.fullmatch
        # Legacy Python lacks Pattern.fullmatch. Anchor the whole expression.
        return scheme, port, 'regex', re.compile('(?:%s)\\Z' % value['regex'], pattern.flags).match
    import ipaddress
    return scheme, port, 'cidr', ipaddress.ip_network(six.text_type(value['cidr']))


class CredentialTargets(object):
    DEFAULT_PORTS = {'http': 80, 'https': 443}

    @classmethod
    def load_imports(cls, config):
        for target in config.get('metrics', []) + config.get('probes', []):
            cfg = target.get('config')
            if isinstance(cfg, dict) and 'import_credential_targets' in cfg:
                cls._import_rules(cfg, config['covenant']['config_dir'])

    @classmethod
    def _import_rules(cls, cfg, directory):
        source = cfg['import_credential_targets']
        if not isinstance(source, six.string_types) or not source.strip() or '\x00' in source:
            raise CovenantConfigurationError('import_credential_targets requires a YAML file path')
        path = os.path.join(directory, source)
        try:
            with open(path, 'rb') as stream:
                imported = yaml.safe_load(stream)
        except (IOError, OSError, yaml.YAMLError, UnicodeError):
            raise CovenantConfigurationError('cannot read import_credential_targets file %r' % source)

        inline = cfg.get('credential_targets', [])
        if not isinstance(imported, list) or not isinstance(inline, list):
            raise CovenantConfigurationError('imported and inline credential_targets must be lists')
        rules = imported + inline
        cls(rules)
        cfg['credential_targets'] = rules
        del cfg['import_credential_targets']

    def __init__(self, values):
        self.unrestricted = values == ['*']
        try:
            if not isinstance(values, list):
                raise ValueError('expected a list')
            self.rules = [] if self.unrestricted else [_rule(value, self.DEFAULT_PORTS) for value in values]
        except (TypeError, ValueError, re.error) as error:
            raise CovenantConfigurationError('invalid credential_targets: %s' % error)

    def allows(self, url):
        scheme, host, port = _origin(url, self.DEFAULT_PORTS)
        if self.unrestricted:
            return True
        for protocol, number, kind, value in self.rules:
            if protocol != scheme or number != port:
                continue
            if kind == 'host' and host == value:
                return True
            if kind == 'wildcard' and host.partition('.')[2] == value:
                return True
            if kind == 'regex' and value(host):
                return True
            if kind == 'cidr':
                import ipaddress
                try:
                    if ipaddress.ip_address(six.text_type(host)) in value:
                        return True
                except ValueError:
                    pass
        return False


class RedisCredentialTargets(CredentialTargets):
    DEFAULT_PORTS = {'redis': 6379, 'rediss': 6379}
