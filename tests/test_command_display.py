import json
import unittest
from prompt_toolkit.document import Document
from prompt_toolkit.completion import CompleteEvent
from loop_robot.terminal.command_display import format_command_result
from loop_robot.terminal.completion import SlashCompleter

class CommandDisplayTests(unittest.TestCase):
    def test_permissions_groups_preserve_every_rule(self):
        data={'mode':'sim','real_hardware':'disabled','rules':{'web_search':'allow','policy_start':'ask','move_sim':'deny'}}
        text=format_command_result('/permissions',json.dumps(data))
        for fragment in ('Mode: sim','Real hardware: disabled','ALLOW (1)','ASK (1)','DENY (1)','web_search','policy_start','move_sim'):
            self.assertIn(fragment,text)
        self.assertNotIn('{',text)
    def test_other_results_are_readable_and_plain_text_survives(self):
        self.assertEqual(format_command_result('/status','Ready'), 'Ready')
        text=format_command_result('/tools', '{"tools":["web_search"],"active":true}')
        self.assertIn('• web_search',text)
        self.assertIn('active: yes',text)
    def test_permission_selection_lists_actions_without_changing_rules(self):
        rules={'web_search':'allow','move_sim':'deny'}
        completer=SlashCompleter('/permissions', permissions=lambda: rules)
        def matches(text):return list(completer.get_completions(Document(text),CompleteEvent()))
        self.assertEqual([c.text for c in matches('/permissions ')],['ask','deny','allow','default','plan','cautious','yolo'])
        self.assertEqual([c.text for c in matches('/permissions ask w')],['web_search'])
        self.assertEqual(rules,{'web_search':'allow','move_sim':'deny'})
