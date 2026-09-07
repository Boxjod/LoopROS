import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from core.tasks import TaskStore
from terminal.app import App, TOOLS
from terminal.config import load_config, ROOT
from terminal.task_supervisor import TaskSupervisor, load_policy


def coding_worker(pipe, definition, config, key, task, schemas):
    data = json.loads(task)
    def call(name,args):
        pipe.send({'type':'tool','name':name,'arguments':args})
        response = pipe.recv()
        return response.get('result', response)
    if data.get('previous_feedback'):
        call('edit_file',{'path':'probe.py','old_text':'print(0)','new_text':'print(1)'})
    source = call('read_file',{'path':'probe.py'})
    call('python_check',{'path':'probe.py'})
    call('run_python',{'path':'probe.py','expected_sha256':source['sha256']})
    call('task_feedback',{'state':'continue','reason':'Verify real stdout','next_step':'Fix code if stdout differs',
         'checks':[{'tool':'run_python','path':'stdout','equals':'1\n'}, {'tool':'run_python','path':'returncode','equals':0}]})
    pipe.send({'type':'result','result':'Tool evidence returned'})
    pipe.close()


class TaskAutonomyTests(unittest.TestCase):
    def test_manual_policy_supports_backup_edit_execution_and_feedback(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'LOOP_HOME':folder+'/home','LOOP_TASK_AUTOSTART':'0'}):
            root = Path(folder)
            app = App(load_config(),root/'state')
            app.workspace_root = root/'workspace';app.workspace_root.mkdir()
            (app.workspace_root/'probe.py').write_text('print(0)\n')
            app.permissions.set_rule('run_python','allow')
            policy = load_policy(ROOT/'configs/task_runtime.json',{t['function']['name'] for t in TOOLS})
            policy.update(retry_initial_s=1,retry_max_s=1)
            store = TaskStore(root/'tasks.sqlite')
            supervisor = TaskSupervisor(store,policy,{'llm':app.client},TOOLS,app.tool,root/'agents.jsonl',None,worker_target=coding_worker)
            try:
                identity = store.submit({'goal':'Make probe.py print 1'})['id']
                deadline = time.monotonic()+12
                while time.monotonic()<deadline and store.get(identity)['state']!='succeeded':
                    supervisor.poll();time.sleep(.03)
                result = store.get(identity)
                self.assertEqual(result['state'],'succeeded',result['feedback'])
                self.assertEqual(result['attempt'],2)
                backups = list((app.state_dir/'file-backups').glob('*.txt'))
                self.assertTrue(any(p.read_text()=='print(0)\n' for p in backups))
                self.assertEqual((app.workspace_root/'probe.py').read_text(),'print(1)\n')
            finally:
                supervisor.close();app.close()

    def test_schedules_cannot_gain_manual_execution_tools(self):
        data = json.loads((ROOT/'configs/task_runtime.json').read_text())
        data['scheduled_tools'].append('run_python')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'policy.json';path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Scheduled tasks'):
                load_policy(path,{t['function']['name'] for t in TOOLS})
