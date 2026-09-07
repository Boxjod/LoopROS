import json
import re
import unittest
from loop_robot.terminal.markdown import BoldText, SYNTAX
from loop_robot.terminal.tool_display import ToolDisplay
from loop_robot.terminal.colors import tool_call, tool_result
from loop_robot.terminal.session_display import history_lines


def plain(text): return re.sub(r'\x1b\[[0-9;]*m','',text)


class ColorOutputTests(unittest.TestCase):
    def test_python_stream_has_token_colors_without_changing_code(self):
        source='def hello(value=42):\n    # 中文注释\n    return "你好" + str(value)\n'
        renderer=BoldText();output=renderer.ansi('```python\n')
        for chunk in [source[:13],source[13:29],source[29:]]: output+=renderer.ansi(chunk)
        output+=renderer.ansi('```\n',final=True)
        self.assertEqual(plain(output),'Code · python\n'+source)
        for role in ('keyword','number','comment','string'):
            self.assertIn('\x1b[38;5;'+str(SYNTAX[role][1])+'m',output)

    def test_multiline_string_and_preview_do_not_corrupt_stream(self):
        renderer=BoldText();renderer.ansi('```python\n')
        renderer.ansi('text = """first\n')
        before=dict(renderer.__dict__)
        self.assertEqual(''.join(t for _,t in renderer.preview('中文')), '中文')
        self.assertEqual(before,renderer.__dict__)
        value=renderer.ansi('中文\nlast"""\n')
        self.assertEqual(plain(value),'中文\nlast"""\n')

    def test_bounded_diff_summary_and_history(self):
        display=ToolDisplay();display.call('edit_file({"path":"main.py"})')
        receipt=dict(written=True,path='main.py',lines_added=12,lines_removed=1,
                     diff='--- main.py\n+++ main.py\n@@ -1 +1 @@\n-old\n'+'\n'.join('+new'+str(i) for i in range(12)))
        summary=display.result(json.dumps(receipt),7)
        self.assertIn('+12 −1 lines',summary)
        self.assertEqual(len(display.preview),11)
        self.assertIn('/details 7',display.preview[-1])
        history=[{'role':'assistant','tool_calls':[{'id':'x','function':{'name':'edit_file','arguments':'{}'}}]},
                 {'role':'tool','tool_call_id':'x','content':json.dumps(receipt)}]
        rendered='\n'.join(history_lines(history))
        self.assertIn('\x1b[38;5;203m',rendered)
        self.assertIn('+new',plain(rendered))
        self.assertIn('Tool › edit_file',plain(rendered))

    def test_diff_control_sequences_are_displayed_as_text(self):
        display=ToolDisplay()
        display.result(json.dumps(dict(written=True,path='file.py',diff='+hello\x1b[2Jworld')),1)
        self.assertNotIn('\x1b',''.join(display.preview))
        self.assertIn('hello',''.join(display.preview))

    def test_tool_categories_and_detail_errors_have_distinct_colors(self):
        from loop_robot.terminal.colors import tool_role, detail_style, TOOL_STYLES
        names = ['read_file','run_python','edit_file','node_status']
        self.assertEqual([tool_role(name) for name in names], ['inspect','execute','modify','status'])
        self.assertEqual(len({detail_style('12:00:00 '+name+'({})') for name in names}),4)
        self.assertEqual(detail_style('  Error: failed'), TOOL_STYLES['error'])

    def test_semantic_colors_reset(self):
        for text in (tool_call('read_file({"path": "a.py"})'),tool_result('Error: failure · /details 1')):
            self.assertTrue(text.endswith('\x1b[0m'))
        self.assertIn('1;38;5;81',tool_call('read_file({})'))
        self.assertIn('1;38;5;203',tool_result('Error: failure'))
