"""Destination rules for credentials attached to HTTP requests."""
import re

import six
from six.moves.urllib_parse import urlsplit

from covenant.classes.exceptions import CovenantConfigurationError

_DEFAULT_PORTS = {'http': 80, 'https': 443}


def _origin(url):
    parts = urlsplit(url)
    if parts.scheme not in _DEFAULT_PORTS or not parts.hostname:
        raise ValueError('expected HTTP or HTTPS origin')
    port = parts.port if parts.port is not None else _DEFAULT_PORTS[parts.scheme]
    return parts.scheme, parts.hostname.lower(), port


def _rule(value):
    if isinstance(value, six.string_types):
        parts = urlsplit(value)
        scheme, host, port = _origin(value)
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
    if (scheme not in _DEFAULT_PORTS or type(port) is not int or not 1 <= port <= 65535):
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
    def __init__(self, values):
        self.unrestricted = values == ['*']
        try:
            if not isinstance(values, list):
                raise ValueError('expected a list')
            self.rules = [] if self.unrestricted else [_rule(value) for value in values]
        except (TypeError, ValueError, re.error) as error:
            raise CovenantConfigurationError('invalid credential_targets: %s' % error)

    def allows(self, url):
        scheme, host, port = _origin(url)
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
