import unittest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from terminal.app import HELP
from terminal.completion import SlashCompleter


class CompletionTests(unittest.TestCase):
    def test_prefixes_and_editor_commands(self):
        completer = SlashCompleter(HELP)
        def matches(text, cursor=None):
            return [c.text for c in completer.get_completions(
                Document(text, cursor_position=cursor), CompleteEvent())]
        self.assertIn('/switch', matches('/s'))
        self.assertIn('/stop', matches('/s'))
        self.assertTrue(all(c.startswith('/s') for c in matches('/s')))
        self.assertEqual(matches('/sw'), ['/switch'])
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
        self.assertEqual(matches('/resume   ab'),['abc123'])
        self.assertEqual(matches('/permissions allow\nr'),[])
