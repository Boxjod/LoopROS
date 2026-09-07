import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from loop_robot.terminal.tool_groups import ToolGroups
from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config


class ToolGroupTests(unittest.TestCase):
    def test_details_preserve_recorded_metrics_after_reopen(self):
        from loop_robot.terminal.session import SessionStore
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'transcript.sqlite'
            store=SessionStore(path)
            store.record('tool','read_file({"path":"file.py"})')
            event=store.record('result','{"content":"original receipt"}')
            store.record('tool_group',json.dumps({'calls':[{'event_id':event,'time':'12:34:56','elapsed':0.125,'tokens':42}]}))
            store.close()
            store=SessionStore(path)
            try:
                details=store.tool_details(event)
                for expected in ('12:34:56','0.125s','~42 local tokens','original receipt'):
                    self.assertIn(expected,details)
            finally: store.close()

    def test_model_references_unchanged_read_without_repeating_content(self):
        from types import SimpleNamespace
        from loop_robot.terminal.llm import ChatAgent
        requests=[]
        replies=iter([{'tool_calls':[{'id':str(i),'type':'function','function':{'name':'read_file','arguments':'{"path":"file.py"}'}}]} for i in range(2)]+[{'content':'done'}])
        def complete(messages,tools):
            requests.append(list(messages))
            return next(replies)
        count=[]
        def dispatch(name,args):
            count.append(name)
            return {'path':'file.py','sha256':'abc','content':'the complete source',**({'_reused':True} if len(count)>1 else {})}
        agent=ChatAgent(SimpleNamespace(config={},complete=complete),[],dispatch)
        agent.context_provider=lambda text:{'system_prompt':'Read the file','tools':[{'type':'function','function':{'name':'read_file','parameters':{'type':'object'}}}],'max_tool_rounds':3}
        self.assertEqual(agent.reply('Read'),'done')
        receipts=[json.loads(m['content']) for m in requests[-1] if m['role']=='tool']
        self.assertEqual(receipts[0]['content'],'the complete source')
        self.assertNotIn('content',receipts[1])
        self.assertEqual(receipts[1]['reuse_tool_call_id'],'0')

    def test_group_preserves_per_call_clock_time_estimate_and_details(self):
        groups=ToolGroups()
        for i in range(4):
            groups.call('read_file({"path":"file.py"})')
            groups.result(json.dumps({'content':'中文代码'}),i)
        index,rows=groups.flush()
        self.assertEqual((index,len(rows)),(1,4))
        self.assertIn('read_file ×4',groups.label(rows))
        self.assertIn('not API billing',groups.details(1))
        for row in rows:
            self.assertRegex(row['time'],r'^\d\d:\d\d:\d\d$')
            self.assertGreater(row['tokens'],0)
            self.assertGreaterEqual(row['elapsed'],0)
            self.assertIn('/details '+str(row['event_id']),row['summary'])

    def test_local_cache_canonical_paths_pages_mutation_and_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            app=App(load_config(),root/'state');app.workspace_root=root
            try:
                script=root/'sample.py';script.write_text('value=1\n')
                first=app.tool('read_file',{'path':'sample.py'})
                second=app.tool('read_file',{'path':str(script),'limit':160})
                self.assertTrue(second['_reused']);self.assertEqual(second['content'],first['content'])
                script.write_text('value=2\n')
                self.assertNotIn('_reused',app.tool('read_file',{'path':'sample.py'}))
                app.permissions.set_rule('read_file','deny')
                with self.assertRaises(PermissionError):app.tool('read_file',{'path':'sample.py'})
                app.permissions.set_rule('read_file','allow')
                app.local_read_cache={}
                self.assertNotIn('_reused',app.tool('read_file',{'path':'sample.py'}))
            finally:app.close()
