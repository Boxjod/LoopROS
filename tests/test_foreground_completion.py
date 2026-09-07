import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from loop_robot.terminal.llm import ChatAgent
from loop_robot.terminal.session_task import SessionTask


class ForegroundCompletionTests(unittest.TestCase):
    def test_transport_timeout_is_distinct_from_other_api_errors(self):
        from urllib.error import URLError
        from unittest.mock import patch
        from loop_robot.terminal.llm import QwenClient, ModelAPITimeout
        client = QwenClient({'protocol': 'openai', 'base_url': 'https://example.invalid',
            'model': 'fixture', 'api_key_env': 'UNUSED_TEST_KEY', 'timeout_s': 60})
        client.key = 'fixture-key'
        with patch('loop_robot.terminal.llm.build_opener') as opener, patch('loop_robot.terminal.llm.model_https_handler'):
            opener.return_value.open.side_effect = URLError(TimeoutError())
            with self.assertRaisesRegex(ModelAPITimeout, '60s'):
                client.complete([], [])

    def test_model_timeout_retries_request_without_replaying_tool(self):
        from loop_robot.terminal.llm import ModelAPITimeout
        task = self.task(); requests = []; executed = []
        def complete(messages, tools):
            requests.append(json.loads(json.dumps(messages)))
            if len(requests) == 1:
                return {'tool_calls': [{'id': 'run', 'type': 'function',
                    'function': {'name': 'observe', 'arguments': '{}'}}]}
            if len(requests) == 2:
                raise ModelAPITimeout('Model timeout')
            return {'content': 'Verified'}
        def dispatch(name, args):
            executed.append(name); task.receipt(name, args, {'done': True})
            return {'done': True}
        agent, _ = self.make_agent([], task, dispatch); agent.client.complete = complete
        with patch('loop_robot.terminal.llm.wait_model_retry'):
            self.assertEqual(agent.reply('Execute'), 'Verified')
        self.assertEqual(executed, ['observe'])
        self.assertEqual(requests[1], requests[2])

    def test_model_retry_is_bounded_and_auth_failure_not_retried(self):
        from loop_robot.terminal.llm import ModelAPITimeout, ModelAPIError
        for error, expected in ((ModelAPITimeout('timeout'), 5),
                                (ModelAPIError('bad request', status=400), 5),
                                (ModelAPIError('unavailable', status=503), 5),
                                (ModelAPIError('auth', status=401), 1)):
            attempts = []
            def complete(messages, tools):
                attempts.append(1)
                raise error
            agent, _ = self.make_agent([], self.task()); agent.client.complete = complete
            with patch('loop_robot.terminal.llm.wait_model_retry') as wait:
                with self.assertRaises(type(error)): agent.reply('Execute')
                self.assertEqual([c.args[0] for c in wait.call_args_list], [2, 4, 8, 16] if expected == 5 else [])
            self.assertEqual(len(attempts), expected)

    def test_real_client_http_400_retries_five_times(self):
        from urllib.error import HTTPError
        from loop_robot.terminal.llm import QwenClient, ModelAPIError
        client = QwenClient({'protocol': 'openai', 'base_url': 'https://example.invalid',
            'model': 'fixture', 'api_key_env': 'UNUSED_TEST_KEY', 'timeout_s': 60})
        client.key = 'fixture-key'
        agent, _ = self.make_agent([], self.task()); agent.client = client
        with patch('loop_robot.terminal.llm.build_opener') as opener, patch('loop_robot.terminal.llm.model_https_handler'), patch('loop_robot.terminal.llm.wait_model_retry'):
            opener.return_value.open.side_effect = HTTPError('https://example.invalid', 400, 'bad request', {}, None)
            with self.assertRaises(ModelAPIError) as raised:
                agent.reply('Execute')
            self.assertEqual(raised.exception.status, 400)
            self.assertEqual(opener.return_value.open.call_count, 5)

    def test_retry_backoff_can_be_stopped(self):
        from threading import Event
        from loop_robot.terminal.llm import wait_model_retry
        stop = Event(); stop.set()
        with self.assertRaisesRegex(RuntimeError, 'Master stopped'):
            wait_model_retry(16, stop)

    def test_compact_receipts_preserve_short_output_and_scope(self):
        task = SessionTask(); task.begin('run')
        task.update({'state': 'active', 'checks': [{'tool': 'run_python', 'path': 'returncode', 'equals': 0}]})
        task.receipt('run_python', {}, {'returncode': 0, 'stdout': 'observations=1100', 'stderr': 'x' * 1500})
        compact = task.snapshot(compact=True)
        result = compact['receipts'][-1]['result']
        self.assertEqual(result['stdout'], 'observations=1100')
        self.assertTrue(result['stderr_preview_truncated'])
        self.assertEqual(compact['current_turn_review']['verdict'], 'pass')
        self.assertEqual(len(task.snapshot()['receipts'][-1]['result']['stderr']), 1500)
        task.begin('run')  # Repeated words are still a new request.
        self.assertNotEqual(task.snapshot(compact=True)['current_turn_review']['verdict'], 'pass')

    def test_contract_can_start_without_invented_fields(self):
        task = SessionTask(); task.begin('Execute')
        task.update({'state': 'active', 'checks': []})
        self.assertIsNotNone(task.continuation())
        with self.assertRaisesRegex(ValueError, 'no output field'):
            task.update({'checks': [{'tool': 'run_python', 'path': 'output.host_ready', 'equals': True}]})
        self.assertEqual(task.snapshot()['checks'], [])
        task.receipt('run_python', {}, {'stdout': 'observed\n', 'returncode': 0})
        task.update({'checks': [{'tool': 'run_python', 'path': 'stdout', 'equals': 'observed\n'}]})
        self.assertIsNone(task.continuation())

    def test_missing_field_diagnostic_preserves_unverified_state(self):
        task = self.task()
        task.receipt('observe', {}, {'frames': 3})
        pending = task.continuation()
        self.assertEqual(pending['check_diagnostics'][0]['available_fields'], ['frames'])
        self.assertEqual(pending['review']['verdict'], 'fail')

    def test_progress_with_calls_is_shown_before_execution(self):
        task = self.task(); events = []; count = []
        def complete(messages, tools, on_event, stop_event):
            count.append(1)
            if len(count) == 1:
                on_event('answer_delta', '已取得状态，继续执行。')
                return {'content': '已取得状态，继续执行。', '_streamed': True,
                    'tool_calls': [{'id': 'run', 'type': 'function',
                        'function': {'name': 'observe', 'arguments': '{}'}}]}
            return {'content': 'Verified'}
        def dispatch(name, args):
            self.assertIn(('answer_delta', '已取得状态，继续执行。'), events)
            task.receipt(name, args, {'done': True})
            return {'done': True}
        agent, _ = self.make_agent([], task, dispatch)
        agent.client.complete = complete; agent.streaming = True
        agent.on_event = lambda *event: events.append(event)
        self.assertEqual(agent.reply('Execute'), 'Verified')
        self.assertEqual(events.count(('answer_delta', '已取得状态，继续执行。')), 1)

    def test_real_python_execution_after_premature_final(self):
        import os,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from loop_robot.terminal.app import App
        from loop_robot.terminal.config import load_config
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,LOOP_HOME=folder+'/home',LOOP_TASK_AUTOSTART='0'):
            app=App(load_config(),Path(folder)/'state');app.workspace_root=Path(folder)
            try:
                app.permissions.set_rule('run_python','allow')
                path=Path(folder)/'probe.py';path.write_text('print("completed")\n')
                task=app.session_task;task.begin('Run probe')
                task.update({'state':'active','checks':[{'tool':'run_python','path':'stdout','equals':'completed\n'}]})
                receipt=app.tool('read_file',{'path':str(path)})
                call={'tool_calls':[{'id':'execute','type':'function','function':{'name':'run_python',
                    'arguments':json.dumps({'path':str(path),'expected_sha256':receipt['sha256']})}}]}
                def dispatch(name,args):
                    result=app.tool(name,args);task.receipt(name,args,result);return result
                agent,requests=self.make_agent([{'content':'Ready to run next'},call,{'content':'Done'}],task,dispatch)
                agent.context_provider=lambda text:{'system_prompt':'Execute','max_tool_rounds':None,
                    'tools':[t for t in app.agent.tools if t['function']['name']=='run_python']}
                self.assertEqual(agent.reply('Execute'),'Done')
                self.assertIsNone(task.continuation())
                self.assertEqual(task.snapshot()['state'],'complete')
                self.assertTrue(Path(task.snapshot()['receipts'][-1]['result']['report']).exists())
            finally:app.close()

    def test_premature_streamed_final_is_not_shown_as_final_answer(self):
        task=self.task();events=[];count=[]
        def complete(messages,tools,on_event,stop_event):
            count.append(1)
            if len(count)==1:
                on_event('answer_delta','Not executed; next step is available')
                return {'content':'Not executed; next step is available','_streamed':True}
            task.receipt('observe',{}, {'done':True})
            on_event('answer_delta','Verified')
            return {'content':'Verified','_streamed':True}
        agent,_=self.make_agent([],task)
        agent.client.complete=complete;agent.streaming=True;agent.on_event=lambda *e:events.append(e)
        self.assertEqual(agent.reply('Execute'),'Verified')
        self.assertEqual([v for k,v in events if k=='answer_delta'],['Verified'])

    def make_agent(self, replies, task, dispatch=None):
        sequence=iter(replies)
        requests=[]
        def complete(messages, tools):
            requests.append((list(messages),list(tools)))
            return next(sequence)
        agent=ChatAgent(SimpleNamespace(config={},complete=complete),[],dispatch or (lambda *a:{}))
        agent.completion_gate=task.continuation
        agent.context_provider=lambda text: {'system_prompt':'Execute requested work','max_tool_rounds':None,
            'tools':[{'type':'function','function':{'name':'observe','parameters':{'type':'object'}}}]}
        return agent,requests

    def task(self):
        task=SessionTask();task.begin('Run one operation')
        task.update({'goal':'Run one operation','state':'active','checks':[{'tool':'observe','path':'done','equals':True}]})
        return task

    def test_unfinished_prose_continues_to_receipt_without_restarting(self):
        task=self.task();calls=[]
        def dispatch(name,args):
            calls.append(name)
            result={'done':True};task.receipt(name,args,result);return result
        tool={'tool_calls':[{'id':'run1','type':'function','function':{'name':'observe','arguments':'{}'}}]}
        agent,requests=self.make_agent([{'content':'Not executed. Next step is to run it.'},tool,{'content':'Verified'}],task,dispatch)
        self.assertEqual(agent.reply('Execute'),'Verified')
        self.assertEqual(calls,['observe'])
        self.assertEqual(len(requests),3)
        self.assertTrue(any(m['role']=='system' and 'Continue now' in str(m['content']) for m in requests[1][0]))
        self.assertNotIn('Not executed',agent.history[-1]['content'])

    def test_discussion_and_old_contract_do_not_auto_resume(self):
        task=self.task();task.begin('Explain this code')
        agent,requests=self.make_agent([{'content':'Explanation'}],task)
        self.assertEqual(agent.reply('Explain'),'Explanation')
        self.assertEqual(len(requests),1)

    def test_concrete_waiting_input_allows_reply(self):
        task=self.task();task.update({'state':'waiting_input','next_step':'Need dataset path'})
        agent,requests=self.make_agent([{'content':'Need dataset path'}],task)
        self.assertEqual(agent.reply('Execute'),'Need dataset path')
        self.assertEqual(len(requests),1)

    def test_repeated_prose_cannot_loop_forever_or_gain_authority(self):
        task=self.task()
        agent,requests=self.make_agent([{'content':'Next step remains'}]*7,task)
        agent.reply('Execute')
        self.assertEqual(len(requests),7)
        self.assertFalse(requests[-1][1])
        self.assertEqual(agent.context_report['loop_stop_reason'],'repeated_without_new_evidence')
        self.assertEqual([m['content'] for m in requests[-1][0] if m['role']=='user'],['Execute'])

    def test_cancel_is_not_overridden_by_unfinished_contract(self):
        import threading
        task=self.task();agent,requests=self.make_agent([],task)
        agent.stop_event=threading.Event();agent.stop_event.set()
        with self.assertRaisesRegex(RuntimeError,'stopped'):
            agent.reply('Execute')
        self.assertEqual(requests,[])
