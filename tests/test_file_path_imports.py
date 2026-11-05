import os
import tempfile
import unittest

import yaml

from covenant.classes.exceptions import CovenantConfigurationError
from covenant.services.file_path_imports import load_file_path_imports


class FilePathImportsTests(unittest.TestCase):
    def test_invalid_import_cannot_remove_restrictions(self):
        with tempfile.TemporaryDirectory() as directory:
            for option in ('import_state_include_paths', 'import_state_exclude_paths'):
                endpoint = {'plugin': 'filestat', option: 'rules.yml'}
                for contents in (None, '[', '{}', '[123]', "['(']", "['']"):
                    with self.subTest(option=option, contents=contents):
                        if contents is not None:
                            with open(os.path.join(directory, 'rules.yml'), 'w') as stream:
                                stream.write(contents)
                        with self.assertRaises(CovenantConfigurationError):
                            load_file_path_imports(endpoint, [{}], directory)
                os.remove(os.path.join(directory, 'rules.yml'))

    def test_empty_import_requires_an_effective_inclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, 'empty.yml'), 'w') as stream:
                yaml.safe_dump([], stream)
            endpoint = {'plugin': 'filestat', 'import_state_include_paths': 'empty.yml'}
            with self.assertRaises(CovenantConfigurationError):
                load_file_path_imports(endpoint, [{}], directory)
            target = {'config': {'include_paths': '^/ready$'}}
            load_file_path_imports(endpoint, [target], directory)
            self.assertEqual(target['config']['include_paths'], ['^/ready$'])
