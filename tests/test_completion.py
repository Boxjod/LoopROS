import unittest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from loop_robot.terminal.app import HELP
from loop_robot.terminal.completion import SlashCompleter


class CompletionTests(unittest.TestCase):
    def test_prefixes_and_editor_commands(self):
        completer = SlashCompleter(HELP)
        def matches(text, cursor=None):
            return [c.text for c in completer.get_completions(
                Document(text, cursor_position=cursor), CompleteEvent())]
        self.assertIn('/switch', matches('/s'))
        self.assertIn('/stop', matches('/s'))
        self.assertTrue(all(c.startswith('/s') for c in matches('/s')))
        self.assertEqual(matches('/sw'), ['/switch', '/switch setup', '/switch list', '/switch reload', '/switch master', '/switch expert'])
        self.assertIn('/queue', matches('/'))
        self.assertIn('/shortcuts', matches('/'))
        self.assertEqual(len(matches('/')), len(set(matches('/'))))
        for text in ('hello', '', '/unknown', '/switch setup', '/s\n', ' /s'):
            self.assertEqual(matches(text), [])
        self.assertEqual(matches('/switch', 3), [])
        completion = next(completer.get_completions(Document('/sw'), CompleteEvent()))
        self.assertEqual(completion.start_position, -3)

    def test_argument_completion_accepts_spacing_but_not_multiline_commands(self):
        completer=SlashCompleter(HELP,permissions=lambda:{'run_sim':'deny'},sessions=lambda:[{'id':'abc123','title':'session','turns':1,'updated':'today'}])
        def matches(text):return [c.text for c in completer.get_completions(Document(text),CompleteEvent())]
        self.assertEqual(matches('/permissions  allow   r'),['run_sim'])
        self.assertEqual(matches('/permissions\task\tr'),['run_sim'])
        self.assertEqual(matches('/resume   ab'),['session'])
        self.assertEqual(matches('/permissions allow\nr'),[])

    def test_switch_subcommands_after_space(self):
        completer = SlashCompleter(HELP)
        def matches(text):
            return list(completer.get_completions(Document(text), CompleteEvent()))
        self.assertEqual([c.text for c in matches('/switch ')], ['setup', 'list', 'reload', 'master', 'expert'])
        self.assertEqual([c.text for c in matches('/switch   se')], ['setup'])
        self.assertEqual(matches('/switch se')[0].start_position, -2)
        self.assertEqual(matches('/switch setup '), [])
        self.assertEqual(matches(' /switch '), [])
        self.assertEqual(matches('/switch\nse'), [])

    def test_partial_parent_includes_full_subcommands(self):
        completer = SlashCompleter(HELP)
        choices = list(completer.get_completions(Document('/swi'), CompleteEvent()))
        setup = next(c for c in choices if c.text == '/switch setup')
        self.assertEqual(setup.start_position, -4)
        self.assertIn('Configure provider', setup.display_meta_text)
        root = list(completer.get_completions(Document('/'), CompleteEvent()))
        self.assertFalse(any(' ' in c.text for c in root))


    def test_agent_role_and_title_completion(self):
        rows=[{'agent_id':'abc','reference':'@1','title':'检查上下文','role':'Reader','state':'running'},
              {'agent_id':'def','reference':'@2','title':'检查权限','role':'Reviewer','state':'done'}]
        completer=SlashCompleter(HELP,agents=lambda:rows,roles=lambda:['Reader','Reviewer'])
        def matches(text): return list(completer.get_completions(Document(text),CompleteEvent()))
        self.assertEqual([c.text for c in matches('/spawn Rea')],['Reader'])
        self.assertEqual([c.text for c in matches('/send 检查')],['@1'])
        self.assertEqual([c.text for c in matches('/result 检查')],['@1','@2'])
        self.assertEqual([c.text for c in matches('/agent-messages @2')],['@2'])
        self.assertEqual(matches('/send @1 不要改变地址'),[])
        self.assertEqual(matches('/send @1 '),[])
