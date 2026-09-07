import json
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from core.tasks import TaskStore, assess
from terminal.task_supervisor import TaskSupervisor, load_policy
from terminal.config import ROOT


def worker(pipe,definition,config,key,task,schemas):
    data=json.loads(task)
    if data['goal']=='inherited tools':
        assert 'agents_status' in {s['function']['name'] for s in schemas}
        pipe.send({'type':'tool','name':'agents_status','arguments':{}})
        pipe.recv()
        pipe.send({'type':'result','result':'Checked inherited tool'})
    elif data['goal']=='crash':
        raise RuntimeError('Model unavailable')
    if data['goal']=='fabricate':
        pipe.send({'type':'result','result':'All done; review pass!'})
    elif data['goal']=='missing':
        pipe.send({'type':'tool','name':'task_feedback','arguments':{'state':'needs_input','reason':'Need motor model','next_step':'Provide motor model'}});pipe.recv()
        pipe.send({'type':'result','result':'Waiting'})
    elif data['goal']=='wait': time.sleep(30)
    elif data['goal'] in ('define checks','weaken checks'):
        expected = 0 if data['goal']=='weaken checks' else 1
        pipe.send({'type':'tool','name':'task_feedback','arguments':{'state':'continue','reason':'Observed interface','next_step':'Verify measurement','checks':[{'tool':'observe','path':'value','equals':expected}]}});pipe.recv()
        value = 1 if data.get('previous_feedback') and data['goal']=='define checks' else 0
        pipe.send({'type':'tool','name':'observe','arguments':{'value':value}});pipe.recv()
        pipe.send({'type':'result','result':'Measurement returned'})
    else:
        previous=data.get('previous_feedback',{})
        value=1 if previous and data['goal']=='improve' else 0
        pipe.send({'type':'tool','name':'observe','arguments':{'value':value}});pipe.recv()
        pipe.send({'type':'result','result':'Attempt finished'})
    pipe.close()


class TaskSupervisorTests(unittest.TestCase):
    def test_manual_inherits_catalog_and_dispatches_through_shared_gate(self):
        from terminal.files import schema
        from unittest.mock import Mock
        dispatch = Mock(return_value={'value':1})
        supervisor = TaskSupervisor(self.store, self.policy,
            {'llm':SimpleNamespace(config={},key=None,resolved_key=lambda:None)},
            [schema('agents_status','Status',{},[])], dispatch, self.path/'inherited.jsonl', [], worker_target=worker)
        try:
            self.assertIn('agents_status', supervisor.runtime.definitions['TaskWorker']['tools'])
            self.assertNotIn('agents_status', supervisor.runtime.definitions['TaskScheduled']['tools'])
            identity = self.store.submit({'goal':'inherited tools','checks':[{'tool':'agents_status','path':'value','equals':1}]})['id']
            end = time.monotonic()+5
            while time.monotonic()<end and self.store.get(identity)['state'] != 'succeeded':
                supervisor.poll()
                time.sleep(.02)
            self.assertEqual(self.store.get(identity)['state'], 'succeeded')
            dispatch.assert_called_once_with('agents_status', {})
        finally:
            supervisor.close()

    def test_worker_defines_missing_checks_and_iterates_against_receipts(self):
        identity = self.store.submit({'goal':'define checks'})['id']
        first = self.until(identity,{'retry_wait'})
        self.assertEqual(first['spec']['checks'],[{'tool':'observe','path':'value','equals':1}])
        self.assertEqual(self.until(identity,{'succeeded'})['attempt'],2)

    def test_worker_cannot_weaken_existing_checks(self):
        identity = self.add('weaken checks')
        result = self.until(identity,{'retry_wait'})
        self.assertEqual(result['spec']['checks'][0]['equals'],1)
        self.assertEqual(result['feedback']['review']['verdict'],'fail')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.store=TaskStore(self.path/'tasks.sqlite')
        self.policy={'max_workers':2,'attempt_timeout_s':10,'retry_initial_s':1,'retry_max_s':3,'stalled_attempts':2,
                     'worker_tools':['observe'],'scheduled_tools':['observe'],'schedules':[],'triggers':[]}
        self.supervisor=TaskSupervisor(self.store,self.policy,{'llm':SimpleNamespace(config={},key=None,resolved_key=lambda: None)},[],lambda name,args:{'value':args['value']},self.path/'agents.jsonl',[],worker_target=worker)

    def tearDown(self): self.supervisor.close();self.temp.cleanup()

    def add(self,goal,checks=True):
        return self.store.submit({'goal':goal,'checks':[{'tool':'observe','path':'value','equals':1}] if checks else []})['id']

    def until(self,identity,states,minimum=0):
        end=time.monotonic()+5
        while time.monotonic()<end:
            self.supervisor.poll();task=self.store.get(identity)
            if task['state'] in states and task['attempt']>=minimum: return task
            time.sleep(.02)
        self.fail(str(task))

    def test_feedback_drives_real_second_process_to_success(self):
        identity=self.add('improve')
        first=self.until(identity,{'retry_wait'})
        self.assertEqual(first['feedback']['review']['verdict'],'fail')
        second=self.until(identity,{'succeeded'})
        self.assertEqual(second['attempt'],2)
        events=self.store.history(identity)
        pids=[e['data']['pid'] for e in events if e['kind']=='attempt']
        self.assertEqual(len(set(pids)),2)
        self.assertEqual(len([e for e in events if e['kind']=='tool_intent']),2)
        self.assertEqual(len(self.store.receipts(identity)),2)

    def test_prose_cannot_complete_and_stall_replans(self):
        identity=self.add('fabricate')
        task=self.until(identity,{'retry_wait'},minimum=2)
        self.assertNotEqual(task['state'],'succeeded')
        self.assertTrue(task['feedback']['needs_replan'])
        replanned=self.until(identity,{'retry_wait'},minimum=3)
        self.assertEqual(replanned['feedback']['phase'],'replan')
        self.store.cancel(identity)

    def exhaust(self, identity):
        end = time.monotonic() + 6
        while time.monotonic() < end:
            with self.store.db() as db:
                db.execute("UPDATE tasks SET due=0 WHERE id=?", (identity,))
            self.supervisor.poll()
            task = self.store.get(identity)
            if task['state'] == 'waiting_input': return task
            time.sleep(.02)
        self.fail(str(task))

    def test_stall_survives_replanning_and_report_stops_model_work(self):
        self.policy['max_replans'] = 1
        identity = self.add('fabricate')
        task = self.exhaust(identity)
        self.assertEqual(task['attempt'], 4)  # two failures, one replan, one verification
        self.assertEqual(task['feedback']['stop_reason'], 'stalled')
        report = Path(task['report_path'])
        self.assertIn('Automatic retries paused', report.read_text())
        self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        for _ in range(5): self.supervisor.poll()
        self.assertEqual(self.store.get(identity)['attempt'], 4)
        resumed = self.store.resume(identity, message='New verified condition')
        self.assertEqual(resumed['feedback']['budget_start'], 4)
        self.assertNotIn('needs_replan', resumed['feedback'])

    def test_three_replans_each_get_a_verification_attempt(self):
        self.policy['stalled_attempts'] = 3
        identity = self.add('fabricate')
        task = self.exhaust(identity)
        self.assertEqual(task['attempt'], 9)
        self.assertEqual(task['feedback']['replans'], 3)
        self.assertEqual(task['feedback']['phase'], 'execute')
        self.assertEqual(task['feedback']['stop_reason'], 'stalled')

    def test_replanner_reads_only_tools_granted_to_its_origin(self):
        policy = {**self.policy, 'worker_tools':['observe','read_file','web_search','web_fetch','write_file'],
                  'scheduled_tools':['observe','web_fetch']}
        supervisor = TaskSupervisor(self.store, policy, self.supervisor.runtime.clients, [],
                                    lambda *a: None, self.path/'grants.jsonl', [], worker_target=worker)
        try:
            self.assertEqual(supervisor.runtime.definitions['TaskReplanner']['tools'],
                             ['task_feedback','read_file','web_search','web_fetch'])
            self.assertEqual(supervisor.runtime.definitions['TaskScheduledReplanner']['tools'],
                             ['task_feedback','web_fetch'])
        finally:
            supervisor.close()

    def test_pretool_failures_have_finite_attempt_budget(self):
        self.policy['max_attempts'] = 2
        identity = self.add('crash')
        task = self.exhaust(identity)
        self.assertEqual(task['attempt'], 2)
        self.assertEqual(task['feedback']['stop_reason'], 'attempt_budget')
        self.assertFalse(self.store.receipts(identity))
        self.assertIn('budget exhausted', Path(task['report_path']).read_text())

    def test_success_report_uses_receipts_without_copying_secrets(self):
        identity = self.add('improve')
        task = self.until(identity, {'succeeded'})
        report = Path(task['report_path']).read_text()
        self.assertIn('Verdict: pass', report)
        self.assertIn('Check 1: PASS', report)
        self.assertIn('Attempts: 2', report)
        # Arbitrary goals and output are kept in the private ledger, not duplicated.
        other = self.store.submit({'goal':'sk-secret-example'})['id']
        self.store.cancel(other)
        self.assertNotIn('sk-secret-example', Path(self.store.get(other)['report_path']).read_text())

    def test_missing_input_and_acceptance_are_not_success(self):
        identity=self.add('missing',False)
        task=self.until(identity,{'waiting_input'})
        self.assertEqual(task['feedback']['reason'],'Need motor model')
        events=self.store.history(identity)
        with self.assertRaisesRegex(ValueError,'Missing acceptance checks'):
            self.store.resume(identity)
        self.assertEqual(self.store.get(identity),task)
        self.assertEqual(self.store.history(identity),events)
        resumed=self.store.resume(identity,message='Motor model supplied')
        self.assertEqual(resumed['state'],'queued')
        self.store.cancel(identity)
        identity=self.add('fabricate',False)
        self.assertEqual(self.until(identity,{'waiting_acceptance'})['state'],'waiting_acceptance')

    def test_cancel_and_recovery_do_not_replay(self):
        identity=self.add('wait');self.supervisor.poll()
        self.store.cancel(identity);self.supervisor.poll()
        self.assertEqual(self.store.get(identity)['state'],'cancelled')
        self.assertFalse(self.supervisor.running)
        other=self.add('wait');self.store.update(other,'running',agent_id='lost')
        self.supervisor.close()
        self.supervisor=TaskSupervisor(self.store,self.policy,{'llm':SimpleNamespace(config={},key=None,resolved_key=lambda: None)},[],lambda *a:None,self.path/'other.jsonl',[],worker_target=worker)
        self.assertEqual(self.store.get(other)['state'],'waiting_observation')
        self.supervisor.poll();self.assertEqual(self.store.get(other)['attempt'],0)

    def test_named_trigger_and_schedule_coalesce_and_persist(self):
        spec={'goal':'configured','checks':[{'tool':'observe','path':'value','equals':1}]}
        self.policy['triggers']=[{'name':'device_rule','enabled':True,'event':'device.ready','task':spec}]
        self.policy['schedules']=[{'name':'health','enabled':True,'every_s':60,'task':spec}]
        self.store.signal('device.ready',{})
        self.supervisor.fire_events();self.supervisor.fire_events()
        self.assertEqual(len(self.store.list()),1)
        with self.store.db() as db: db.execute('UPDATE schedules SET due=0')
        self.supervisor.fire_events();self.assertEqual(len(self.store.list()),2)
        self.store.cancel(next(t['id'] for t in self.store.list() if t['spec']['origin']=='schedule'))
        with self.store.db() as db: db.execute('UPDATE schedules SET due=0')
        self.supervisor.fire_events();self.assertEqual(len(self.store.list()),3)

    def test_invalid_policy_and_failed_receipt(self):
        from terminal.app import TOOLS
        policy=load_policy(ROOT/'configs/task_runtime.json',{t['function']['name'] for t in TOOLS})
        self.assertEqual(policy['max_workers'],108)
        self.assertEqual(policy['max_replans'],3)
        self.assertEqual(policy['max_attempts'],9)
        self.assertIn('skill_run', policy['worker_tools'])
        unsafe = {**policy, 'scheduled_tools':policy['scheduled_tools'] + ['skill_run']}
        unsafe_path = self.path/'unsafe.json'
        unsafe_path.write_text(json.dumps(unsafe))
        with self.assertRaisesRegex(ValueError, 'Scheduled tasks'):
            load_policy(unsafe_path,{t['function']['name'] for t in TOOLS})
        legacy = {k:v for k,v in policy.items() if k not in ('max_attempts','max_replans')}
        path = self.path/'legacy.json'
        path.write_text(json.dumps(legacy))
        self.assertEqual(load_policy(path,{t['function']['name'] for t in TOOLS})['max_replans'],3)
        checks=[{'tool':'observe','path':'value','equals':True}]
        self.assertEqual(assess(checks,[{'tool':'observe','result':{'value':1}}])['verdict'],'fail')
        self.assertEqual(assess(checks,[{'tool':'observe','result':{'value':True,'error':'bad'}}])['verdict'],'fail')

    def test_only_explicit_submission_creates_persistent_task(self):
        from terminal.app import App
        from terminal.config import load_config
        from unittest.mock import patch
        app=App(load_config(),self.path/'app')
        try:
            with patch('terminal.task_service.start',return_value={'process_alive':True}) as start, patch.object(app.client,'complete',return_value={'content':'Need more evidence.'}):
                app.agent.reply('修复机器人控制代码')
                start.assert_not_called()
                store=TaskStore(app.state_dir/'tasks.sqlite')
                self.assertFalse(store.list())
                result=app.tool('task_submit',{'goal':'Explicit supervised goal'})
                self.assertEqual(len(store.list()),1)
                self.assertEqual(result['task']['spec']['goal'],'Explicit supervised goal')
                start.assert_called_once()
        finally: app.close()
