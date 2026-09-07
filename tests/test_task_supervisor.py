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

    def test_missing_input_and_acceptance_are_not_success(self):
        identity=self.add('missing',False)
        self.assertEqual(self.until(identity,{'waiting_input'})['state'],'waiting_input')
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
