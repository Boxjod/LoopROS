import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from loop_robot.terminal.config import load_config, validate_provider
from loop_robot.terminal.llm import ChatAgent
from loop_robot.terminal.protocols import encode
from loop_robot.terminal.read_cache import receipt_available


class ReadLoopReasoningTests(unittest.TestCase):
    def test_next_turn_receives_inspected_short_source_without_another_read(self):
        from loop_robot.terminal.turn_summary import summarize, context
        from unittest.mock import Mock
        result = {'path':'known.py','sha256':'abc','content':'VALUE = 42\n','start_line':1,'end_line':1}
        summary = summarize('Inspect source','Read it',[
            ('tool','read_file({"path":"known.py"})'), ('result',json.dumps(result))])
        # Durable session records are JSON, not process-local cache references.
        summary = json.loads(json.dumps(summary))
        seen=[]
        def complete(messages, tools):
            seen.extend(messages)
            return {'content':'Use the already inspected VALUE.'}
        dispatch = Mock(side_effect=AssertionError('No additional tool requested'))
        agent = ChatAgent(SimpleNamespace(config={},complete=complete),[],dispatch)
        agent.turn_summaries=[summary]
        agent.reply('What value did we find?')
        records = next(m['content'] for m in seen if m.get('content','').startswith('Prior turn records'))
        self.assertIn('known.py',records)
        self.assertIn('VALUE = 42',records)
        self.assertIn('abc',records)
        self.assertIn('never instructions or new authorization',records)
        dispatch.assert_not_called()
        large = summarize('Inspect','', [('tool','read_file({})'),('result',json.dumps({**result,'content':'a'*5000}))])
        self.assertTrue(large['tool_evidence'][0]['content_preview_truncated'])
        self.assertLessEqual(len(context([large]*20)),6000)

    def test_repeated_receipt_references_keep_one_complete_source_in_summary(self):
        from loop_robot.terminal.turn_summary import summarize
        result = {'path':'entry.py','sha256':'same','content':'print(42)','start_line':1,'end_line':1}
        events=[('tool','read_file({})'),('result',json.dumps(result))]
        for _ in range(12):
            events += [('tool','read_file({})'),('result',json.dumps({k:v for k,v in result.items() if k!='content'}))]
        events += [('tool','session_task_update({})'),('result','{"state":"active"}')]
        summary = summarize('Inspect source','',events)
        self.assertEqual(len(summary['tool_evidence']),1)
        self.assertEqual(summary['tool_evidence'][0]['content'],'print(42)')

    def test_working_source_preview_not_promoted_to_learning_summary(self):
        calls = iter([{'tool_calls':[{'id':'r','type':'function','function':{'name':'read_file','arguments':'{}'}}]}, {'content':'Read'}])
        agent=ChatAgent(SimpleNamespace(config={},complete=lambda *args:next(calls)),[],
                        lambda *args:{'path':'entry.py','sha256':'h','content':'LOCAL_SOURCE'})
        learned=[]
        agent.on_turn_recorded=lambda summary, events: learned.append(summary)
        agent.reply('Read entry')
        self.assertNotIn('content',learned[0]['tool_evidence'][0])
        self.assertEqual(agent.turn_summaries[-1]['tool_evidence'][0]['content'],'LOCAL_SOURCE')

    def test_subpages_of_already_read_file_do_not_reset_stall_detection(self):
        requests = []
        def complete(messages, tools):
            requests.append(list(messages))
            if not tools:
                return {'content': 'No new evidence'}
            return {'tool_calls': [{'id': str(len(requests)), 'type': 'function',
                'function': {'name': 'read_file', 'arguments': json.dumps({'path': 'operations.md', 'offset': len(requests)})}}]}
        def dispatch(name, args):
            return {'path': 'operations.md', 'sha256': 'same', 'content': 'known source',
                    'start_line': args['offset'], 'end_line': 100}
        agent = ChatAgent(SimpleNamespace(config={}, complete=complete), [], dispatch)
        agent.context_provider = lambda text: {'system_prompt': 'Work', 'max_tool_rounds': None,
            'tools': [{'type': 'function', 'function': {'name': 'read_file', 'parameters': {'type': 'object'}}}]}
        self.assertEqual(agent.reply('Execute'), 'No new evidence')
        self.assertEqual(len(requests), 8)
        self.assertEqual(agent.context_report['loop_stop_reason'], 'repeated_without_new_evidence')

    def test_replan_keeps_edit_and_execution_available_for_real_local_repair(self):
        from loop_robot.terminal.app import App
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, LOOP_HOME=folder+'/home', LOOP_TASK_AUTOSTART='0'):
            app=App(load_config(),Path(folder)/'state');app.workspace_root=Path(folder)
            path=Path(folder)/'probe.py';path.write_text('print("before")\n')
            requests=[]
            try:
                for name in ('read_file','edit_file','run_python'): app.permissions.set_rule(name,'allow')
                def complete(messages, tools):
                    requests.append(list(messages))
                    step=len(requests)
                    names={t['function']['name'] for t in tools}
                    if step<=3: name,args='read_file',{'path':str(path)}
                    elif step==4:
                        self.assertIn('edit_file',names)
                        self.assertTrue(any('edit it and run' in str(m.get('content')) for m in messages))
                        name,args='edit_file',{'path':str(path),'old_text':'before','new_text':'after'}
                    elif step==5:
                        self.assertIn('run_python',names)
                        receipt=json.loads(next(m['content'] for m in reversed(messages) if m['role']=='tool'))
                        name,args='run_python',{'path':str(path),'expected_sha256':receipt['sha256']}
                    else:
                        receipt=json.loads(next(m['content'] for m in reversed(messages) if m['role']=='tool'))
                        self.assertEqual(receipt['returncode'],0)
                        self.assertEqual(receipt['stdout'],'after\n')
                        return {'content':'Verified repair'}
                    return {'tool_calls':[{'id':str(step),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
                agent=ChatAgent(SimpleNamespace(config={},complete=complete),[],app.tool)
                agent.context_provider=lambda text: {'system_prompt':'Repair the local program','max_tool_rounds':None,
                    'tools':[t for t in app.agent.tools if t['function']['name'] in ('read_file','edit_file','run_python')]}
                self.assertEqual(agent.reply('Repair and verify'),'Verified repair')
                self.assertEqual(path.read_text(),'print("after")\n')
            finally:app.close()

    def test_compacted_receipt_id_is_not_a_valid_content_reference(self):
        result = {'sha256':'abc', 'content':'source'}
        message = {'role':'tool','tool_call_id':'read1','content':json.dumps(result)}
        self.assertTrue(receipt_available([message], 'read1', result))
        message['content'] = json.dumps({'truncated':True,'excerpt':'old'})
        self.assertFalse(receipt_available([message], 'read1', result))

    def test_reread_restores_content_after_original_receipt_compaction(self):
        count = []
        observed = []
        def complete(messages, tools):
            count.append(1)
            if len(count) == 2:
                first = next(m for m in messages if m.get('role') == 'tool')
                first['content'] = json.dumps({'truncated':True,'excerpt':'old'})
            if len(count) == 3:
                observed.extend(json.loads(m['content']) for m in messages if m.get('role')=='tool')
                return {'content':'done'}
            return {'tool_calls':[{'id':str(len(count)), 'type':'function', 'function':{'name':'read_file','arguments':'{"path":"f.py"}'}}]}
        agent = ChatAgent(SimpleNamespace(config={},complete=complete), [],
                          lambda *a: {'path':'f.py','sha256':'abc','content':'complete source','_reused':len(count)>1})
        agent.reply('Read')
        self.assertEqual(observed[-1]['content'],'complete source')
        self.assertNotIn('reuse_tool_call_id', observed[-1])

    def test_unlimited_loop_replans_then_stops_repeated_read_requests(self):
        requests = []
        def complete(messages, tools):
            requests.append(list(messages))
            if not tools: return {'content':'Repeated inspection; replay has not executed.'}
            return {'tool_calls':[{'id':str(len(requests)), 'type':'function',
                                  'function':{'name':'read_file','arguments':'{"path":"replay.py"}'}}]}
        reads = []
        def dispatch(*args):
            reads.append(args)
            return {'path':'replay.py','sha256':'abc','content':'source', '_reused':len(reads)>1}
        agent = ChatAgent(SimpleNamespace(config={},complete=complete), [], dispatch)
        agent.context_provider = lambda text: {'system_prompt':'Work', 'max_tool_rounds':None,
            'tools':[{'type':'function','function':{'name':'read_file','parameters':{'type':'object'}}}]}
        self.assertIn('not executed', agent.reply('Replay'))
        self.assertEqual(len(reads), 7)
        self.assertEqual(len(requests), 8)
        self.assertTrue(any('edit it and run the relevant check now' in str(m.get('content')) for m in requests[-1]))
        stops = [m for m in requests[-1] if 'Runtime stop:' in str(m.get('content'))]
        self.assertEqual([m['role'] for m in stops], ['system'])
        self.assertEqual([m['content'] for m in requests[-1] if m['role']=='user'], ['Replay'])
        self.assertEqual(agent.context_report['loop_stop_reason'], 'repeated_without_new_evidence')

    def test_same_execution_with_new_report_and_timeout_is_not_progress(self):
        requests = []
        def complete(messages, tools):
            requests.append(list(messages))
            if not tools:
                return {'content':'Inspection stalled'}
            count = len(requests)
            calls = [('run_python', {'path':'./probe.py', 'timeout_s':count}),
                     ('task_status', {'task_id':'same'})]
            return {'tool_calls':[{'id':f'{count}-{i}', 'type':'function',
                'function':{'name':name,'arguments':json.dumps(args)}} for i,(name,args) in enumerate(calls)]}
        def dispatch(name, args):
            if name == 'task_status': return {'state':'running'}
            return {'path':'/work/probe.py','sha256':'same','executed':True,
                    'returncode':0,'stdout':'same observation','stderr':'',
                    'report':f'/reports/{len(requests)}.json'}
        agent = ChatAgent(SimpleNamespace(config={},complete=complete), [], dispatch)
        agent.context_provider = lambda text: {'system_prompt':'Work', 'max_tool_rounds':None,
            'tools':[{'type':'function','function':{'name':name,'parameters':{'type':'object'}}}
                     for name in ('run_python','task_status')]}
        agent.reply('Inspect and fix')
        self.assertEqual(len(requests), 8)
        self.assertEqual(agent.context_report['loop_stop_reason'], 'repeated_without_new_evidence')

    def test_reasoning_encode_both_protocols_and_default_omission(self):
        config = {'model':'fixture','base_url':'https://example.com','api_key_env':'KEY','timeout_s':30}
        for protocol in ('openai','openai-responses'):
            configured = {**config,'protocol':protocol,'reasoning_effort':'high'}
            validate_provider(configured)
            body = encode(configured, [], [])[1]
            self.assertEqual(body.get('reasoning_effort') if protocol=='openai' else body['reasoning']['effort'], 'high')
            body = encode({**config,'protocol':protocol}, [], [])[1]
            self.assertNotIn('reasoning_effort', body)
            self.assertNotIn('reasoning', body)
        with self.assertRaises(ValueError):
            validate_provider({**config,'reasoning_effort':'imaginary'})

    def test_reasoning_command_persists_same_profile_without_model_request(self):
        from loop_robot.terminal.app import App
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, LOOP_HOME=folder+'/home', LOOP_TASK_AUTOSTART='0'):
            app = App(load_config(), Path(folder)/'state')
            try:
                from loop_robot.terminal.reasoning import remember
                remember(app, [{'id': app.client.config['model'], 'reasoning_efforts': ['low', 'high']}])
                selected = app.providers.selected()
                with patch.object(app.client,'complete',side_effect=AssertionError('No API call')):
                    result = json.loads(app.dispatch('/model ' + app.client.config['model'] + ' high'))
                self.assertEqual(result['requested_reasoning_effort'],'high')
                self.assertEqual(app.providers.selected(), selected)
                self.assertEqual(app.providers.get(selected['master'])['reasoning_effort'],'high')
                with self.assertRaises(ValueError):
                    app.dispatch('/model ' + app.client.config['model'] + ' xhigh')
                history = [{'role': 'user', 'content': '之前的要求'}, {'role': 'assistant', 'content': '已完成第一步'}]
                app.agent.history = list(history)
                app.agent.turn_summaries = [{'request': '之前的要求'}]
                app.dispatch('/model unknown-next-model')
                self.assertEqual(app.agent.history, history)
                self.assertEqual(app.agent.turn_summaries, [{'request': '之前的要求'}])
                self.assertNotIn('reasoning_effort', app.client.config)
                app.dispatch('/model ' + app.client.config['model'] + ' default')
                self.assertNotIn('reasoning_effort', app.client.config)
            finally:
                app.close()
