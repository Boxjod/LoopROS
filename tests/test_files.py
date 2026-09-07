import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terminal.files import read_file


class ReadFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, text):
        path = self.directory / name
        path.write_text(text, encoding='utf-8')
        return path

    def test_reads_whole_file(self):
        path = self.write('a.txt', 'line1\nline2\nline3')
        result = read_file(str(path))
        self.assertEqual(result['content'], 'line1\nline2\nline3')
        self.assertEqual(result['total_lines'], 3)
        self.assertEqual(result['start_line'], 1)
        self.assertEqual(result['end_line'], 3)
        self.assertNotIn('next_offset', result)

    def test_offset_and_limit_paginate_with_next_offset(self):
        path = self.write('a.txt', '\n'.join(str(n) for n in range(1, 11)))
        result = read_file(str(path), offset=3, limit=2)
        self.assertEqual(result['content'], '3\n4')
        self.assertEqual(result['start_line'], 3)
        self.assertEqual(result['end_line'], 4)
        self.assertEqual(result['next_offset'], 5)

    def test_offset_beyond_end_raises(self):
        path = self.write('a.txt', 'only one line')
        with self.assertRaises(ValueError):
            read_file(str(path), offset=5)

    def test_missing_file_raises_value_error(self):
        with self.assertRaises(ValueError):
            read_file(str(self.directory / 'missing.txt'))

    def test_directory_is_rejected(self):
        with self.assertRaises(ValueError):
            read_file(str(self.directory))

    def test_binary_file_is_rejected(self):
        path = self.directory / 'b.bin'
        path.write_bytes(b'\xff\xfe\x00\x01')
        with self.assertRaises(ValueError):
            read_file(str(path))

    def test_sqlite_extension_is_denied_even_if_text(self):
        path = self.write('state.sqlite', 'not really sqlite but still denied')
        with self.assertRaises(ValueError):
            read_file(str(path))

    def test_relative_path_resolves_against_project_root(self):
        result = read_file('pyproject.toml')
        self.assertIn('loop-ros', result['content'])

    def test_credentials_file_is_denied(self):
        home = tempfile.TemporaryDirectory()
        try:
            with patch.dict(os.environ, {'LOOP_HOME': home.name}):
                credentials = Path(home.name) / 'credentials.json'
                credentials.write_text('{"secret": "key"}', encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_file(str(credentials))
        finally:
            home.cleanup()

    def test_large_content_is_truncated_with_marker(self):
        path = self.write('big.txt', 'x' * (70 * 1024))
        result = read_file(str(path))
        self.assertEqual(result['truncated'], 'byte_limit')
        self.assertLessEqual(len(result['content'].encode('utf-8')), 64 * 1024)


class AppReadFileWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        from terminal.app import App
        from terminal.config import load_config
        self.App, self.load_config = App, load_config
        self.app = self.App(self.load_config(), self.temp.name)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_read_file_reachable_with_no_permission_prompt(self):
        result = self.app.tool('read_file', {'path': 'README.md'})
        self.assertIn('path', result)
        self.assertIn('content', result)
