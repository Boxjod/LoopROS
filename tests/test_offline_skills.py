import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config
from loop_robot.terminal.offline_skills import node_name
from loop_robot.toolchain.offline_skill import save_profile, inspect, package, materialize
from loop_robot.toolchain.process_node import config


@unittest.skipUnless(os.name=='posix', 'Bash integration runs on POSIX')
class OfflineSkillTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,LOOP_HOME=str(self.root/'home'),LOOP_TASK_AUTOSTART='0')
        self.env.start()
        self.app=App(load_config(),self.root/'state')
        self.app.client.complete=lambda *a,**k: self.fail('Offline commands must not call model API')
        self.app.permissions.set_rule('run_python','allow')
        self.app.permissions.set_rule('skill_export','allow')
        directory=self.root/'home/processes';directory.mkdir(exist_ok=True)
        script='print("中文离线启动",flush=True); import time; time.sleep(30)'
        stop='from pathlib import Path; Path("stopped").write_text("yes")'
        (directory/'fixture.json').write_text(json.dumps(dict(argv=[sys.executable,'-u','-c',script],cwd=str(self.root),stop_argv=[sys.executable,'-c',stop])))

    def tearDown(self):
        self.app.close();self.env.stop();self.temp.cleanup()

    def wait(self,name):
        until=time.monotonic()+6
        while time.monotonic()<until:
            state=self.app.nodes.status(node_name(name))
            if '中文离线启动' in state['snapshot'].get('output_tail',''): return state
            if state['state']=='failed': self.fail(str(state))
            time.sleep(.03)
        self.fail('No script output')

    def test_named_inspection_skips_catalog_and_changed_package_rejects_run(self):
        self.app.tool('skill_export', {'profile':'fixture','name':'fixture-start','title':'Fixture start'})
        with patch('loop_robot.toolchain.offline_skill.catalog', side_effect=AssertionError('No full catalog scan')):
            value = self.app.tool('skill_executables', {'name':'fixture-start'})
        self.assertEqual(len(value['skills']), 1)
        inspected = value['skills'][0]
        root = Path(inspected['path'])
        script = next((root/'scripts').glob('*.sh'))
        script.write_text(script.read_text() + '\n# changed version\n')
        with patch.object(self.app.nodes, 'start', side_effect=AssertionError('Must not start changed code')):
            with self.assertRaisesRegex(ValueError, 'Skill changed'):
                self.app.tool('skill_run', {'name':'fixture-start','expected_sha256':inspected['sha256']})

    def test_export_run_logs_and_stop_with_no_api_and_snapshot(self):
        self.app.dispatch('/skills save fixture start-host 启动机械臂 Host')
        self.assertIn('启动机械臂 Host',self.app.dispatch('/skills'))
        root=self.root/'home/skills/start-host'
        self.assertTrue((root/'scripts/start.sh').is_file())
        self.app.dispatch('/skills run 启动机械臂 Host')
        self.wait('start-host')
        self.assertIn('中文离线启动',self.app.dispatch('/skills logs 启动机械臂 Host'))
        with self.assertRaises(ValueError): self.app.dispatch('/skills run 启动机械臂 Host')
        # Removing the source package must not remove this run's stop script.
        shutil.rmtree(root)
        self.app.dispatch('/skills stop 启动机械臂 Host')
        self.assertEqual((self.root/'stopped').read_text(),'yes')
        self.assertFalse(self.app.nodes.status(node_name('start-host'))['process_alive'])
        self.assertEqual(self.app.resources.status()['reservations_by_workload'],{})

    def test_hash_gate_read_only_and_permissions(self):
        data=save_profile('fixture','saved-host','启动Host')
        self.assertFalse(self.app.nodes.records)
        self.app.tool('skill_read',{'name':'saved-host'})
        self.assertFalse(self.app.nodes.records)
        path=self.root/'home/skills/saved-host/scripts/start.sh'
        path.write_text(path.read_text()+'\n# changed\n')
        with self.assertRaises(ValueError): config(dict(skill='saved-host',expected_sha256=data['sha256']))
        self.app.permissions.set_mode('plan')
        with self.assertRaises(PermissionError): self.app.dispatch('/skills run 启动Host')
        self.app.permissions.set_mode('sim');self.app.permissions.set_rule('run_python','deny')
        with self.assertRaises(PermissionError): self.app.dispatch('/skills run 启动Host')
        with self.assertRaises(ValueError): save_profile('fixture','saved-host','Overwrite')
        self.assertEqual(len(self.app.nodes.records),0)
        for tool in ('skill_run','skill_export'):
            with self.assertRaises(ValueError): self.app.scheduled_tool(tool,{})

    def test_path_escape_and_platform_validation(self):
        save_profile('fixture','saved-host','启动Host')
        root=self.root/'home/skills/saved-host'
        manifest=json.loads((root/'run.json').read_text())
        manifest['platforms']['nt']={'start':'scripts/start.cmd'}
        (root/'scripts/start.cmd').write_text('@echo off\necho hello\n')
        (root/'run.json').write_text(json.dumps(manifest))
        self.assertTrue(package('saved-host','nt')['supported'])
        manifest['platforms']['posix']['start']='../outside.sh'
        (root/'run.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): inspect('saved-host')
        manifest['platforms']['posix']['start']='scripts/link.sh'
        (root/'run.json').write_text(json.dumps(manifest))
        (root/'scripts/link.sh').symlink_to(self.root/'home/processes/fixture.json')
        with self.assertRaises(ValueError): inspect('saved-host')

    def test_export_approval_round_trip_and_completion(self):
        self.app.permissions.set_rule('skill_export','ask')
        with self.assertRaises(PermissionError): self.app.dispatch('/skills save fixture saved-host 启动Host')
        request=next(iter(self.app.permissions.requests()))
        self.app.dispatch('/approve '+request)
        from loop_robot.terminal.completion import SlashCompleter
        from loop_robot.terminal.app import HELP
        from prompt_toolkit.document import Document
        completer=SlashCompleter(HELP)
        self.assertIn('启动Host',[c.text for c in completer.get_completions(Document('/skills run 启'),None)])

    def test_literal_bash_arguments_and_script_exit_receipt(self):
        directory=self.root/'home/processes'
        literal='$(touch NOT_ALLOWED);中文 & | " $HOME'
        (directory/'echo.json').write_text(json.dumps(dict(argv=[sys.executable,'-c','import sys; print(sys.argv[1])',literal],cwd=str(self.root))))
        data=save_profile('echo','echo-literal','输出参数')
        spec,folder=materialize(dict(skill='echo-literal',expected_sha256=data['sha256']))
        try:
            import subprocess
            result=subprocess.run(spec['argv'],cwd=spec['cwd'],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.stdout.strip(),literal)
            self.assertFalse((self.root/'NOT_ALLOWED').exists())
        finally:folder.cleanup()
