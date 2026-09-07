from pathlib import Path
import tempfile
import unittest

from loop_robot.terminal.media import mentioned_image


class MentionedImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'logo.png'
        self.path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * 16)

    def tearDown(self):
        self.temp.cleanup()

    def test_quoted_path_embedded_in_prose_is_found(self):
        text = "'{}'帮我分析一下这个图片".format(self.path)
        result = mentioned_image(text)
        self.assertEqual(len(result), 1)
        label, parts = result[0]
        self.assertEqual(label, str(self.path))
        self.assertEqual(parts[0]['type'], 'image_url')
        self.assertTrue(parts[0]['image_url']['url'].startswith('data:image/png;base64,'))

    def test_bare_path_in_sentence_is_found(self):
        text = 'please look at {} and tell me what it is'.format(self.path)
        self.assertEqual(mentioned_image(text)[0][0], str(self.path))

    def test_nonexistent_path_is_silently_ignored(self):
        self.assertEqual(mentioned_image("check out '/no/such/file.png' please"), [])

    def test_plain_prose_without_any_path_is_ignored(self):
        self.assertEqual(mentioned_image('just a normal question, no files here'), [])

    def test_non_image_extension_is_ignored(self):
        text_file = Path(self.temp.name) / 'notes.txt'
        text_file.write_text('hello')
        self.assertEqual(mentioned_image("read '{}'".format(text_file)), [])

    def test_directory_with_image_like_suffix_is_ignored(self):
        fake_dir = Path(self.temp.name) / 'weird.png'
        fake_dir_as_dir = Path(self.temp.name) / 'adir'
        fake_dir_as_dir.mkdir()
        self.assertEqual(mentioned_image(str(fake_dir_as_dir) + '.png'), [])

    def test_oversized_image_is_skipped_not_raised(self):
        big = Path(self.temp.name) / 'huge.png'
        big.write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * (8 * 1024 * 1024 + 1))
        self.assertEqual(mentioned_image("'{}'".format(big)), [])
