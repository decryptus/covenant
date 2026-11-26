"""Match network destinations for probe access and credential policies."""
import os
import re
import socket

import six
import yaml
from six.moves.urllib_parse import urlsplit

from covenant.classes.exceptions import CovenantConfigurationError


def _canonical_host(host):
    host = host.lower().rstrip('.')
    if ':' in host:
        import ipaddress
        return six.text_type(ipaddress.IPv6Address(six.text_type(host.split('%', 1)[0])))
    try:
        # Match the IPv4 spellings accepted by socket.connect, including 127.1.
        return socket.inet_ntoa(socket.inet_aton(host))
    except (socket.error, UnicodeError):
        return host.encode('idna').decode('ascii').rstrip('.')


def _origin(url, ports):
    parts = urlsplit(url)
    if parts.scheme not in ports or not parts.hostname:
        raise ValueError('unsupported scheme or missing host')
    port = parts.port if parts.port is not None else ports[parts.scheme]
    if not 1 <= port <= 65535:
        raise ValueError('invalid destination port')
    return parts.scheme, parts.hostname.lower(), port


def _rule(value, ports, canonical_host=False):
    if isinstance(value, six.string_types):
        parts = urlsplit(value)
        scheme, host, port = _origin(value, ports)
        if parts.username is not None or parts.query or parts.fragment or parts.path not in ('', '/'):
            raise ValueError('expected an origin without user information, query or path')
        if host.startswith('*.') and '*' not in host[2:] and len(host) > 2:
            suffix = host[2:]
            return scheme, port, 'wildcard', _canonical_host(suffix) if canonical_host else suffix
        if '*' in host:
            raise ValueError('wildcard must replace the first DNS label')
        return scheme, port, 'host', _canonical_host(host) if canonical_host else host

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


DESTINATION_OPTIONS = ('allowed_targets', 'disallowed_targets')
DESTINATION_KEYS = DESTINATION_OPTIONS + tuple('import_' + key for key in DESTINATION_OPTIONS)


def load_origin_rules(cfg, option, directory):
    key = 'import_' + option
    inline = cfg.get(option, [])
    if key not in cfg:
        return inline
    source = cfg[key]
    if not isinstance(source, six.string_types) or not source.strip() or '\x00' in source:
        raise CovenantConfigurationError('%s requires a YAML file path' % key)
    try:
        with open(os.path.join(directory, source), 'rb') as stream:
            imported = yaml.safe_load(stream)
    except (IOError, OSError, yaml.YAMLError, UnicodeError):
        raise CovenantConfigurationError('cannot read %s file %r' % (key, source))
    if not isinstance(imported, list) or not isinstance(inline, list):
        raise CovenantConfigurationError('imported and inline %s must be lists' % option)
    return imported + inline


class TargetOrigins(object):
    DEFAULT_PORTS = {'http': 80, 'https': 443}
    OPTION = 'allowed_targets'

    def __init__(self, values, option=None):
        self.unrestricted = values == ['*']
        try:
            if not isinstance(values, list):
                raise ValueError('expected a list')
            self.rules = [] if self.unrestricted else [
                _rule(value, self.DEFAULT_PORTS, canonical_host=option == 'disallowed_targets')
                for value in values]
        except (TypeError, ValueError, OverflowError, re.error) as error:
            raise CovenantConfigurationError('invalid %s: %s' % (option or self.OPTION, error))

    def allows(self, url):
        return self.allows_origin(*_origin(url, self.DEFAULT_PORTS))

    def allows_origin(self, scheme, host, port):
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

    def require(self, url):
        if not self.allows(url):
            raise ValueError('destination denied by endpoint target rules')


class EndpointTargets(TargetOrigins):
    def __init__(self, matcher, config):
        self.DEFAULT_PORTS = matcher.DEFAULT_PORTS
        self.allowed = matcher(config.get('allowed_targets', []))
        self.disallowed = matcher(config.get('disallowed_targets', []), option='disallowed_targets')

    def allows_origin(self, scheme, host, port):
        if self.disallowed.unrestricted:
            return False
        if self.disallowed.rules:
            canonical = _canonical_host(host)
            if (self.disallowed.allows_origin(scheme, host, port)
                    or self.disallowed.allows_origin(scheme, canonical, port)):
                return False
            if ':' in canonical:
                import ipaddress
                mapped = ipaddress.IPv6Address(canonical).ipv4_mapped
                if mapped is not None and self.disallowed.allows_origin(scheme, six.text_type(mapped), port):
                    return False
        return self.allowed.allows_origin(scheme, host, port)


class TlsTargetOrigins(TargetOrigins):
    DEFAULT_PORTS = {'tls': 443}


class RedisTargetOrigins(TargetOrigins):
    DEFAULT_PORTS = {'redis': 6379, 'rediss': 6379}


class CredentialTargets(TargetOrigins):
    OPTION = 'credential_targets'

    @classmethod
    def load_imports(cls, config):
        for target in config.get('metrics', []) + config.get('probes', []):
            cfg = target.get('config')
            if isinstance(cfg, dict) and 'import_credential_targets' in cfg:
                rules = load_origin_rules(cfg, cls.OPTION, config['covenant']['config_dir'])
                cls(rules)
                cfg[cls.OPTION] = rules
                del cfg['import_credential_targets']


class RedisCredentialTargets(CredentialTargets):
    DEFAULT_PORTS = RedisTargetOrigins.DEFAULT_PORTS
