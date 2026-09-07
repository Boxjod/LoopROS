import copy
import json
import unittest
from types import SimpleNamespace
from terminal.context_window import select, tool_text, bound_tool_history
from terminal.llm import ChatAgent


class ContextWindowTests(unittest.TestCase):
    def test_complete_groups_and_non_destructive_views(self):
        history = [{'role': role, 'content': str(i)} for i in range(30) for role in ('user', 'assistant')]
        original = copy.deepcopy(history)
        selected, recall, report = select(history)
        self.assertEqual(len(selected), 32)
        self.assertEqual(selected[0]['role'], 'user')
        self.assertIn('- 0', recall)
        self.assertEqual(history, original)
        self.assertEqual(report['omitted_messages'], 28)
        self.assertEqual(len(select(history, 8)[0]), 8)

    def test_steering_inputs_stay_together_and_media_is_not_encoded_text(self):
        history = [{'role':'user','content':'old'}, {'role':'assistant','content':'old reply'},
                   {'role':'user','content':'first'}, {'role':'user','content':'correction'},
                   {'role':'assistant','content':'answer'}]
        self.assertEqual(select(history, 3)[0], history[2:])
        self.assertEqual(select(history, 2)[0], [])
        media = [{'role':'user','content':[{'type':'image_url','image_url':{'url':'x'*100000}}]},
                 {'role':'assistant','content':'seen'}]
        self.assertEqual(select(media)[2]['history_character_units'], 2004)

    def test_long_turn_retains_valid_tool_pairs_and_full_receipts(self):
        source = {'output':'中"\\'*16000}
        text = tool_text(source)
        self.assertLessEqual(len(text), 12000)
        self.assertTrue(json.loads(text)['truncated'])
        messages = []
        for i in range(30):
            messages += [{'role':'assistant','tool_calls':[{'id':str(i)}]},
                         {'role':'tool','tool_call_id':str(i),'content':text}]
        before = len(messages)
        self.assertLessEqual(bound_tool_history(messages), 48000)
        self.assertEqual(len(messages), before)
        self.assertTrue(all(json.loads(m['content']) for m in messages if m['role']=='tool'))
        self.assertEqual(len(source['output']), 48000)

    def test_model_receives_more_short_history_without_losing_archive(self):
        calls=[]
        client=SimpleNamespace(complete=lambda m,t: calls.append(copy.deepcopy(m)) or {'content':'ok'})
        agent=ChatAgent(client,[],lambda *a:None)
        agent.history=[{'role':r,'content':str(i)} for i in range(20) for r in ('user','assistant')]
        agent.reply('continue')
        self.assertEqual(len(agent.history),42)
        self.assertGreater(len(calls[0]),10)
        self.assertIn('Earlier user request excerpts',calls[0][1]['content'])
