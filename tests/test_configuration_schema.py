"""Configuration contracts use XYS without coercing values or initializing services."""
import copy
import unittest
try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

from covenant.classes.configuration_schema import validate_configuration, CovenantConfigurationError


class ConfigurationSchemaTests(unittest.TestCase):
    def test_extensions_and_values_are_preserved_without_mutation(self):
        conf = {'general': {'result_timeout': '30'}, 'endpoints': {'demo': {'plugin': 'fake', 'metrics': [], 'vars': {}, 'extension': 'PRIVATE'}}}
        original = copy.deepcopy(conf)
        self.assertIs(validate_configuration(conf), conf)
        self.assertEqual(conf, original)

    def test_invalid_known_fields_cannot_hide_behind_extensions(self):
        cases = [None,
                 {'general': {}, 'endpoints': []},
                 {'general': {}, 'endpoints': {'a': {'plugin': 'fake', 'metrics': {}}}},
                 {'general': {}, 'endpoints': {'a': {'plugin': 'fake', 'vars': []}}},
                 {'general': {}, 'endpoints': {'a': {'plugin': 'fake', 'import_probes': 42}}}]
        for conf in cases:
            with self.assertRaises(CovenantConfigurationError) as caught:
                validate_configuration(conf)
            self.assertNotIn('PRIVATE', str(caught.exception))

    def test_invalid_values_are_not_in_validation_logs(self):
        with patch('covenant.classes.configuration_schema.xys.LOG') as logger:
            with self.assertRaises(CovenantConfigurationError) as caught:
                validate_configuration({'general': 'PRIVATE-CONFIGURATION-VALUE'})
        self.assertNotIn('PRIVATE-CONFIGURATION-VALUE', str(caught.exception))
        self.assertNotIn('PRIVATE-CONFIGURATION-VALUE', str(logger.mock_calls))

    def test_invalid_file_precedes_module_initialization(self):
        import os
        import tempfile
        from covenant.classes import config
        fd, path = tempfile.mkstemp()
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write('general: [PRIVATE]')
            with patch.object(config.signal, 'signal'), patch.object(config, 'init_modules') as init:
                with self.assertRaises(CovenantConfigurationError):
                    config.load_conf(path)
                init.assert_not_called()
        finally:
            os.unlink(path)

    def test_imported_component_types_and_opaque_values(self):
        from covenant.classes.configuration_schema import validate_component
        for kind in ('metrics', 'probes'):
            value = [{'opaque': {'secret': 'PRIVATE'}}]
            self.assertIs(validate_component(value, kind), value)
            with self.assertRaises(CovenantConfigurationError):
                validate_component({'PRIVATE': 1}, kind)
        self.assertEqual(validate_component({'x': [1, 2]}, 'vars'), {'x': [1, 2]})
        with self.assertRaises(CovenantConfigurationError):
            validate_component([], 'vars')
