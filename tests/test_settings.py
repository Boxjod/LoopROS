import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config
from loop_robot.terminal.permissions import PermissionGate
from loop_robot.terminal.conversation_context import context


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'LOOP_HOME': self.temp.name + '/home'})
        self.env.start()
        self.app = App(load_config(), Path(self.temp.name) / 'state')

    def tearDown(self):
        self.app.close()
        self.env.stop()
        self.temp.cleanup()

    def change(self, target, value):
        return json.loads(self.app.dispatch('/config set ' + target + ' ' + json.dumps(value)))

    def test_default_tools_and_explicit_approval_in_plan(self):
        self.app.dispatch('/mode plan')
        names = {t['function']['name'] for t in context(self.app, '改成真机模式')['tools']}
        self.assertTrue({'settings_read', 'settings_update'} <= names)
        args = {'target': 'permissions', 'value': {'mode': 'hardware'}}
        with self.assertRaisesRegex(PermissionError, 'Approval required'):
            self.app.tool('settings_update', args)
        self.assertEqual(self.app.permissions.snapshot()['mode'], 'plan')
        request = next(iter(self.app.permissions.requests()))
        result = json.loads(self.app.dispatch('/approve ' + request))
        self.assertEqual(result['mode'], 'real')
        self.assertEqual(PermissionGate(self.app.permissions.path).snapshot()['mode'], 'real')
        self.assertEqual(context(self.app, '')['live_context']()['permissions']['mode'], 'real')
        with self.assertRaisesRegex(ValueError, "Approval ID not found"):
            self.app.dispatch('/approve ' + request)

    def test_permission_profiles_deny_and_background(self):
        for profile in ('default', 'plan', 'cautious', 'yolo'):
            self.assertTrue(self.change('permissions', {'profile': profile})['applied'])
        self.change('permissions', {'action': 'settings_update', 'rule': 'deny'})
        with self.assertRaises(PermissionError):
            self.app.tool('settings_update', {'target': 'permissions', 'value': {'mode': 'sim'}})
        with self.assertRaises(ValueError):
            self.app.scheduled_tool('settings_update', {})
        with self.assertRaises(ValueError):
            self.app.dispatch('/config set permissions {"mode":"real"}', scheduled=True)

    def test_profiles_preserve_history_and_isolate_key(self):
        old = dict(self.app.client.config)
        self.app.client.key = 'test-memory-key'
        self.app.agent.history.append({'role': 'user', 'content': 'keep this history'})
        new = {**old, 'base_url': 'https://example.invalid/v1', 'api_key_env': 'ISOLATED_TEST_KEY'}
        self.change('profiles', {'operation': 'save', 'name': 'new', 'config': new})
        self.change('profiles', {'operation': 'use', 'name': 'new'})
        self.assertIsNone(self.app.client.key)
        self.assertEqual(len(self.app.agent.history), 1)
        self.assertEqual(self.app.providers.selected()['master'], 'new')
        self.change('profiles', {'operation': 'save', 'name': 'new', 'config': {**new, 'model': 'changed'}, 'replace': True})
        self.assertEqual(self.app.client.config['model'], 'changed')
        self.change('profiles', {'operation': 'use', 'name': 'default-master'})
        self.assertEqual(self.app.client.key, 'test-memory-key')
        self.change('profiles', {'operation': 'remove', 'name': 'new'})

    def test_config_validation_persistence_and_backup(self):
        value = {'services': {'act': {'argv': ['python', 'service.py'], 'cwd': None}}}
        result = self.change('config', value)
        self.assertFalse(result['applied'])
        path = Path(result['path'])
        self.assertEqual(json.loads(path.read_text()), value)
        for invalid in ({'llm': {'timeout_s': 0}}, {'password': 'secret'}, {'scene': {'backend': 'missing'}}):
            with self.assertRaises(ValueError):
                self.change('config', invalid)
            self.assertEqual(json.loads(path.read_text()), value)
        second = self.change('config', {})
        self.assertEqual(json.loads(Path(second['backup']).read_text()), value)

    def test_roles_policy_and_deployment(self):
        roles = {'Worker': {'provider': 'llm', 'tools': ['run_sim'], 'prompt': 'Work'}}
        self.assertTrue(self.change('agents', roles)['applied'])
        self.assertEqual(self.app.runtime.definitions, roles)
        policy = self.app.tool('settings_read', {'target': 'task_runtime'})['value']
        policy['max_workers'] = 1
        result = self.change('task_runtime', policy)
        self.assertFalse(result['applied'])
        self.assertEqual(Path(result['path']).parent, self.app.state_dir)
        policy['worker_tools'].append('settings_update')
        with self.assertRaises(ValueError):
            self.change('task_runtime', policy)
        manifest = {'version': 1, 'deployment_id': 'test', 'hosts': ['local'],
                    'carriers': [{'id': 'arm', 'host': 'local', 'label': 'Arm', 'adapter': 'sim_arm', 'config': {}}]}
        result = self.change('deployment', {'manifest': manifest, 'host_id': 'local'})
        self.assertTrue(result['configured'])
        self.assertEqual(self.app.nodes.status()['nodes'], [])
        self.assertEqual(self.app.tool('carrier_list', {})['carriers'][0]['carrier_id'], 'arm')

    def test_active_work_blocks_changes_before_persistence(self):
        with patch('loop_robot.terminal.settings.idle', side_effect=ValueError('active work')):
            with self.assertRaises(ValueError):
                self.change('config', {})
        self.assertEqual(self.app.permissions.snapshot()['mode'], 'sim')
        with patch('loop_robot.terminal.task_service.status', return_value={'process_alive': True}):
            with self.assertRaises(ValueError):
                self.change('config', {})
        self.assertFalse((Path(self.temp.name) / 'home/config.json').exists())

    def test_model_tool_loop_changes_mode_with_existing_grant(self):
        self.app.dispatch('/permissions allow settings_update')
        messages = [
            {'tool_calls': [{'id': 'change', 'type': 'function', 'function': {'name': 'settings_update',
                'arguments': json.dumps({'target': 'permissions', 'value': {'mode': 'real'}})}}]},
            {'content': '已切换真机模式。'}]
        with patch.object(self.app.client, 'complete', side_effect=messages), patch.object(self.app.viewer, 'open') as opened:
            answer = self.app.dispatch('改成真机模式')
        self.assertIn('真机', answer)
        self.assertEqual(self.app.permissions.snapshot()['mode'], 'real')
        opened.assert_not_called()

    def test_permission_approval_with_live_supervisor(self):
        args = {'target':'permissions', 'value':{'mode':'real'}}
        with self.assertRaises(PermissionError):
            self.app.tool('settings_update', args)
        request = next(iter(self.app.permissions.requests()))
        with patch('loop_robot.terminal.task_service.status', return_value={'process_alive':True}), patch.object(self.app.viewer,'open') as opened:
            result = json.loads(self.app.dispatch('/approve ' + request))
        self.assertEqual(result['mode'],'real')
        self.assertEqual(result['real_hardware'],'driver_required')
        self.assertNotIn(request,self.app.permissions.requests())
        opened.assert_not_called()

    def test_precondition_retains_exact_request_until_success(self):
        args = {'target':'config','value':{}}
        with self.assertRaises(PermissionError):
            self.app.tool('settings_update',args)
        request = next(iter(self.app.permissions.requests()))
        with patch('loop_robot.terminal.task_service.status', return_value={'process_alive':True}):
            with self.assertRaisesRegex(ValueError,'retained'):
                self.app.dispatch('/approve ' + request)
        self.assertFalse((Path(self.temp.name)/'home/config.json').exists())
        self.assertEqual(self.app.permissions.requests()[request]['args'],args)
        with patch('loop_robot.terminal.task_service.status', return_value={'process_alive':False}):
            result = json.loads(self.app.dispatch('/approve ' + request))
        self.assertTrue(result['saved'])
        self.assertNotIn(request,self.app.permissions.requests())

    def test_approval_is_not_reentrant_or_replayed_after_unknown_effect(self):
        gate = self.app.permissions
        with self.assertRaises(PermissionError):
            gate.check('settings_update',{'target':'config','value':{}})
        request = next(iter(gate.requests()))
        calls = []
        def execute(action,args):
            calls.append(action)
            with self.assertRaisesRegex(ValueError,'already executing'):
                gate.approve(request,execute)
            raise RuntimeError('uncertain execution result')
        with self.assertRaises(RuntimeError):
            gate.approve(request,execute)
        self.assertEqual(calls,['settings_update'])
        with self.assertRaisesRegex(ValueError,'Approval ID not found'):
            gate.approve(request,execute)
