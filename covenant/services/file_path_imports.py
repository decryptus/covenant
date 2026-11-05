"""Load endpoint-scoped filestat path lists before collectors start."""
import os
import re

import six
import yaml

from covenant.classes.exceptions import CovenantConfigurationError


PATH_IMPORTS = (('import_state_include_paths', 'include_paths'),
                ('import_state_exclude_paths', 'exclude_paths'))


def _validate_patterns(option, patterns):
    for pattern in patterns:
        if not isinstance(pattern, six.string_types) or not pattern:
            raise CovenantConfigurationError('%s requires nonempty regex strings' % option)
        try:
            re.compile(six.ensure_binary(pattern))
        except (re.error, ValueError, OverflowError) as error:
            raise CovenantConfigurationError('invalid regex for %s: %s' % (option, error))


def load_file_path_imports(endpoint, targets, directory):
    for option, key in PATH_IMPORTS:
        if option not in endpoint:
            continue
        if endpoint['plugin'] != 'filestat':
            raise CovenantConfigurationError('%s requires the filestat plugin' % option)
        source = endpoint[option]
        if not isinstance(source, six.string_types) or not source.strip() or '\x00' in source:
            raise CovenantConfigurationError('%s requires a YAML file path' % option)
        try:
            with open(os.path.join(directory, source), 'rb') as stream:
                shared = yaml.safe_load(stream)
        except (IOError, OSError, UnicodeError, yaml.YAMLError):
            raise CovenantConfigurationError('cannot read %s file %r' % (option, source))
        if not isinstance(shared, list):
            raise CovenantConfigurationError('%s file must contain a YAML list' % option)
        _validate_patterns(option, shared)
        for target in targets:
            cfg = target.get('config')
            if cfg is None:
                cfg = target['config'] = {}
            if not isinstance(cfg, dict):
                raise CovenantConfigurationError('expected a filestat target config mapping')
            local = cfg.get(key)
            if local is None or local == '':
                local = []
            elif isinstance(local, six.string_types):
                local = [local]
            if not isinstance(local, list):
                raise CovenantConfigurationError('%s must be a regex or list' % key)
            _validate_patterns(key, local)
            if key == 'include_paths' and not (shared or local):
                raise CovenantConfigurationError('imported and local include_paths are both empty')
            cfg[key] = shared + local
