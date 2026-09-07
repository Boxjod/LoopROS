import unittest

from loop_robot.terminal.session_display import history_lines


class SessionDisplayTests(unittest.TestCase):
    def test_safe_history_keeps_roles_media_and_tool_evidence(self):
        history = [
            {'role': 'user', 'content': [{'type': 'text', 'text': '看这张图片'},
                                       {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,SECRET'}}]},
            {'role': 'assistant', 'reasoning_content': '检查记录', 'content': '**答复**\x1b[2J',
             'tool_calls': [{'id': 'a', 'function': {'name': 'web_search', 'arguments': '{"query":"电机"}'}},
                            {'id': 'b', 'function': {'name': 'run_python', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': 'b', 'content': '{"error":"执行失败"}'},
            {'role': 'tool', 'tool_call_id': 'a', 'content': '{"results":[{}],"raw":"HIDDEN_RAW"}'},
            {'role': 'assistant', 'content': '完成答复', '_responses_output': [{'type': 'reasoning', 'encrypted_content': 'SECRET'}]},
        ]
        rendered = '\n'.join(history_lines(history))
        for text in ('❯ 看这张图片', '[media]', '✻ 检查记录', '\x1b[1m答复\x1b[22m',
                     'Tool › Web Search', 'Error: 执行失败', '1 search', '● 完成答复'):
            import re
            self.assertIn(text, rendered if '\x1b' in text else re.sub(r'\x1b\[[0-9;]*m','',rendered))
        for text in ('SECRET', 'HIDDEN_RAW', '\x1b[2J', '/details None', ' · 0.0s'):
            self.assertNotIn(text, rendered)
        self.assertEqual(history[-1]['content'], '完成答复')
