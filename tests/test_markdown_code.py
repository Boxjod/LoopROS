import re
import unittest
from loop_robot.terminal.markdown import BoldText, CODE


def plain(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


class MarkdownCodeTests(unittest.TestCase):
    def test_full_message_code_preserves_commands_and_indentation(self):
        text = '请执行：\n```text\n/approve example-id\n  literal **stars**\n```\n**下一步**'
        result = BoldText().ansi(text, final=True)
        self.assertNotIn('```', result)
        self.assertIn('Code · text\n', plain(result))
        self.assertIn('/approve example-id\n  literal **stars**\n', plain(result))
        self.assertIn('\x1b[1m下一步',result)
        self.assertIn('\x1b[48;5;235m',result)

    def test_split_fences_and_preview_are_stateful_without_mutation(self):
        renderer = BoldText()
        chunks = ['`','``py','thon\n','print("中','文")\n','``','`\n','Done']
        output = ''.join(renderer.ansi(chunk) for chunk in chunks)
        self.assertNotIn('```',plain(output))
        self.assertIn('print("中文")',plain(output))
        self.assertFalse(renderer.code)
        renderer = BoldText()
        renderer.ansi('```sh',line_end=True)
        before = dict(renderer.__dict__)
        self.assertEqual(renderer.preview('echo **literal**'),[(CODE,'echo **literal**')])
        self.assertEqual(renderer.__dict__,before)
        self.assertIn('echo **literal**',renderer.ansi('echo **literal**',line_end=True))
        renderer.ansi('```',line_end=True)
        self.assertFalse(renderer.code)
