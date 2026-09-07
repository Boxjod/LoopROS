import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from terminal.session import SessionStore
from terminal.llm import ChatAgent

CONFIG={'base_url':'https://example.test','model':'test','protocol':'openai'}

class SessionResumeTests(unittest.TestCase):
    def test_rename_search_export_persist_and_isolate_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'conversation.sqlite'
            store = SessionStore(path)
            try:
                store.save(CONFIG, [{'role': 'user', 'content': '电机故障查询'},
                                    {'role': 'assistant', 'content': '状态未知'},
                                    {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,private-media'}}]}], [], draft='unsent draft')
                identity = store.session_id
                store.rename(CONFIG, '左臂排查记录')
                for _ in range(35):
                    store.new_session()
                    store.save(CONFIG, [{'role': 'user', 'content': 'Other session'}], [])
                self.assertEqual(store.list_sessions(CONFIG, query='电机故障')[0]['id'], identity)
                self.assertEqual(store.list_sessions(CONFIG, query='左臂')[0]['title'], '左臂排查记录')
                other = {**CONFIG, 'model': 'other-model'}
                self.assertEqual(store.list_sessions(other, query='左臂'), [])
                with self.assertRaises(ValueError): store.export(other, identity)
                first = store.export(CONFIG, identity)
                second = store.export(CONFIG, identity)
                self.assertNotEqual(first, second)
                output = first.read_text()
                self.assertIn('左臂排查记录', output)
                self.assertIn('状态未知', output)
                self.assertIn('[media omitted]', output)
                self.assertNotIn('private-media', output)
                self.assertNotIn('unsent draft', output)
                self.assertNotIn(CONFIG['base_url'], output)
                store.resume(CONFIG, identity)
                with self.assertRaises(ValueError): store.rename(CONFIG, 'bad\x1bname')
                store.save(CONFIG, store.read_session(CONFIG, identity)['history'], [])
            finally:
                store.close()
            store = SessionStore(path)
            try:
                self.assertEqual(store.list_sessions(CONFIG, query='左臂')[0]['title'], '左臂排查记录')
            finally:
                store.close()

    def test_multiple_sessions_provider_isolation_and_summaries(self):
        with tempfile.TemporaryDirectory() as directory:
            store=SessionStore(Path(directory)/'conversation.sqlite')
            try:
                store.save(CONFIG,[{'role':'user','content':'衣柜'}],[],summaries=[{'request':'衣柜'}])
                first=store.session_id
                store.new_session();store.save(CONFIG,[{'role':'user','content':'电脑'}],[])
                self.assertEqual(len(store.list_sessions(CONFIG)),2)
                self.assertEqual(store.resume(CONFIG,first)['summaries'][0]['request'],'衣柜')
                other={**CONFIG,'base_url':'https://other.test'}
                with self.assertRaises(ValueError): store.resume(other,first)
                store.save(other,[],[])
                self.assertNotEqual(store.session_id,first)
                self.assertEqual(len(store.list_sessions(CONFIG)),2)
                self.assertEqual(len(store.list_sessions(other)),1)
            finally: store.close()

    def test_full_history_preserved_context_bounded_and_summary_unverified(self):
        captured=[]
        def complete(messages,tools):
            captured.append(messages)
            return {'content':'已生成，哈希 a1b2c3'}
        agent=ChatAgent(SimpleNamespace(complete=complete),[],lambda *args:None)
        events=[]
        agent.on_event=lambda kind,value:events.append((kind,value))
        agent.history=[{'role':role,'content':str(i)+'x'*1000} for i in range(30) for role in ('user','assistant')]
        agent.reply('测试')
        self.assertEqual(len(agent.history),62)
        self.assertNotIn('Summary',[kind for kind,value in events])
        self.assertLess(len(captured[0]),15)
        summary=agent.turn_summaries[-1]
        self.assertEqual(summary['status'],'conversation_only')
        self.assertFalse(summary['answer_is_execution_evidence'])
        self.assertEqual(summary['tool_evidence'],[])

    def test_failed_turn_still_has_summary(self):
        def fail(*args): raise RuntimeError('network failure')
        agent=ChatAgent(SimpleNamespace(complete=fail),[],lambda *args:None)
        with self.assertRaises(RuntimeError): agent.reply('继续')
        self.assertEqual(agent.turn_summaries[-1]['status'],'error')
        self.assertEqual(agent.turn_summaries[-1]['request'],'继续')

    def test_resume_completion_selects_real_sessions(self):
        from terminal.completion import SlashCompleter
        from prompt_toolkit.document import Document
        from prompt_toolkit.completion import CompleteEvent
        rows=[{'id':'abc123','title':'衣柜','turns':2,'updated':'2026-09-05'}]
        completer=SlashCompleter('',sessions=lambda:rows)
        result=list(completer.get_completions(Document('/resume a'),CompleteEvent()))
        self.assertEqual(result[0].text,'衣柜')
        self.assertEqual(result[0].start_position,-1)
