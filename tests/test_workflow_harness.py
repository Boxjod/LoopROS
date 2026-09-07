import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config
from loop_robot.terminal.session import SessionStore
from loop_robot.terminal.session_task import SessionTask
from model_fixture import call


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'LOOP_HOME': str(self.root / 'home'), 'LOOP_TASK_AUTOSTART': '0'})
        self.env.start()
        self.app = App(load_config(), self.root / 'state')
        self.app.workspace_root = self.root / 'workspace'
        self.app.workspace_root.mkdir()
        for action in ('tool_write', 'tool_run'):
            self.app.permissions.set_rule(action, 'allow')

    def tearDown(self):
        self.app.close()
        self.env.stop()
        self.temp.cleanup()

    def save_tool(self, source, **extra):
        return self.app.tool('tool_write', {'name': 'calculate', 'description': 'Calculate a JSON result', 'source': source, **extra})

    def test_author_debug_fix_run_and_portability(self):
        invalid = self.save_tool('def broken(:')
        self.assertFalse(invalid['valid'])
        self.assertFalse((self.root / 'home/tools/calculate.json').exists())
        first = self.save_tool('raise ValueError("debug-me")')
        result = self.app.tool('tool_run', {'name': 'calculate', 'expected_sha256': first['sha256']})
        self.assertNotEqual(result['returncode'], 0)
        self.assertIn('debug-me', result['stderr'])
        second = self.save_tool('import json, sys\nprint(json.dumps({"value": int(sys.argv[1]) * 2}))', expected_sha256=first['sha256'])
        self.assertTrue(Path(second['backup']).exists())
        with self.assertRaises(ValueError):
            self.app.tool('tool_run', {'name': 'calculate', 'expected_sha256': first['sha256']})
        other = self.root / 'portable-home'
        shutil.copytree(self.root / 'home/tools', other / 'tools')
        with patch.dict(os.environ, {'LOOP_HOME': str(other)}):
            read = self.app.tool('tool_read', {'name': 'calculate'})
            result = self.app.tool('tool_run', {'name': 'calculate', 'expected_sha256': read['sha256'], 'arguments': ['21']})
        self.assertEqual(result['output'], {'value': 42})
        self.assertEqual(json.loads(Path(result['report']).read_text())['output'], {'value': 42})
        self.assertTrue(Path(result['report']).is_file())
        self.assertEqual(result['task_success'], 'not_evaluated')

    def test_tool_approval_deny_syntax_and_path_boundaries(self):
        script = self.app.workspace_root / 'bad.py'
        script.write_text('x = (')
        check = self.app.tool('python_check', {'path': 'bad.py'})
        self.assertEqual(check['line'], 1)
        self.assertFalse(check['executed'])
        saved = self.save_tool('print("ok")')
        args = {'name': 'calculate', 'expected_sha256': saved['sha256']}
        self.app.permissions.set_rule('tool_run', 'ask')
        with self.assertRaises(PermissionError):
            self.app.tool('tool_run', args)
        request = next(iter(self.app.permissions.requests()))
        approved = json.loads(self.app.dispatch('/approve ' + request))
        self.assertEqual(approved['stdout'].strip(), 'ok')
        self.app.permissions.set_rule('tool_run', 'allow')
        self.app.permissions.set_rule('run_python', 'deny')
        with self.assertRaises(PermissionError):
            self.app.tool('tool_run', args)
        self.app.permissions.set_mode('plan')
        with self.assertRaises(PermissionError):
            self.save_tool('print(1)', expected_sha256=saved['sha256'])
        with self.assertRaises(ValueError):
            self.app.tool('tool_read', {'name': '../escape'})
        with self.assertRaises(ValueError):
            self.app.scheduled_tool('tool_run', args)

    def test_session_task_persist_resume_and_no_prose_success(self):
        task = self.app.session_task
        task.begin('修复并验证计算')
        task.update({'plan': ['检查', '修复', '验证'], 'checks': [{'tool': 'tool_run', 'path': 'output.value', 'equals': 42}]})
        with self.assertRaises(ValueError):
            task.update({'state': 'complete'})
        task.receipt('tool_run', {}, {'returncode': 1, 'stderr': 'bad'})
        task.receipt('tool_run', {}, {'returncode': 0, 'output': {'value': 42}})
        task.update({'state': 'complete'})
        store = SessionStore(self.root / 'sessions.sqlite')
        try:
            store.save(self.app.client.config, [{'role': 'user', 'content': '修复并验证计算'}], [], task=task.snapshot())
            first = store.session_id
            self.assertEqual(store.read_session(self.app.client.config, first)['task']['session_id'], first)
            store.new_session()
            store.save(self.app.client.config, [], [])
            self.assertNotEqual(first, store.session_id)
            self.assertEqual(store.read_session(self.app.client.config, store.session_id)['task']['state'], 'idle')
            restored = SessionTask(store.resume(self.app.client.config, first)['task'])
            self.assertEqual(restored.snapshot()['state'], 'complete')
            self.assertEqual(restored.snapshot()['feedback'][0]['error'], 'nonzero_exit')
            restored.begin('再验证一次')
            with self.assertRaises(ValueError):
                restored.update({'state': 'complete'})
        finally:
            store.close()

    def test_model_feedback_loop_fails_fixes_and_verifies(self):
        responses = [call('session_task_update', plan=['编写', '运行', '修复', '验证'], checks=[{'tool': 'tool_run', 'path': 'output.value', 'equals': 42}]),
                     call('tool_write', name='calculate', description='Test', source='raise RuntimeError("wrong")')]
        phase = {'n': 0}
        seen = []
        def complete(messages, tools):
            seen.append(messages)
            if responses:
                return responses.pop(0)
            spec = self.app.tool('tool_read', {'name': 'calculate'})
            phase['n'] += 1
            if phase['n'] in (1, 3):
                return call('tool_run', name='calculate', expected_sha256=spec['sha256'])
            if phase['n'] == 2:
                return call('tool_write', name='calculate', description='Fixed', source='print(\'{"value":42}\')', expected_sha256=spec['sha256'])
            if phase['n'] == 4:
                return call('session_task_update', state='complete', progress='实测 value=42')
            return {'content': '已修复，实测输出 42。'}
        with patch.object(self.app.client, 'complete', side_effect=complete):
            answer = self.app.agent.reply('编写计算工具并验证输出42')
        self.assertIn('42', answer)
        self.assertEqual(self.app.session_task.snapshot()['state'], 'complete')
        self.assertTrue(self.app.session_task.snapshot()['feedback'])
        self.assertTrue(any('Workflow harness' in str(m) for m in seen[0]))
        self.assertEqual(self.app.nodes.status()['nodes'], [])

    def test_harness_override_and_identical_failure_limit(self):
        inherited = self.app.tool('harness_read', {'path': 'harness/workflow.md'})
        self.assertTrue(inherited['inherited_default'])
        self.app.permissions.set_rule('harness_write', 'allow')
        self.app.tool('harness_write', {'path': 'harness/workflow.md', 'content': 'Custom workflow: inspect evidence before completion.'})
        from loop_robot.terminal.conversation_context import context
        prompt = context(self.app, '')['system_prompt']
        self.assertIn('Custom workflow', prompt)
        self.assertNotIn('After two equivalent failures', prompt)
        saved = self.save_tool('raise RuntimeError("repeat")')
        repeated = call('tool_run', name='calculate', expected_sha256=saved['sha256'])
        with patch.object(self.app.client, 'complete', side_effect=[repeated, repeated, repeated, {'content': '需要检查错误原因'}]):
            self.app.agent.reply('调试工具')
        receipts = self.app.session_task.snapshot()['receipts']
        self.assertEqual(sum(r['result'].get('executed', False) for r in receipts), 2)
        self.assertEqual(receipts[-1]['result']['error'], 'RepeatedFailure')
        self.assertEqual(self.app.session_task.snapshot()['state'], 'needs_review')


class SessionTaskInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_creates_task_resume_restores_without_execution(self):
        from prompt_toolkit.application import create_app_session
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        from loop_robot.terminal.interactive import Terminal
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOOP_HOME': directory + '/home'}), create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(directory) / 'state')
                terminal = Terminal(app)
                try:
                    app.session_task.begin('原任务')
                    app.session_task.update({'plan': ['检查状态'], 'next_step': '读取回执'})
                    terminal.checkpoint()
                    old = terminal.store.session_id
                    with patch.object(app.client, 'complete', side_effect=AssertionError('No model call')), patch.object(app, 'tool', side_effect=AssertionError('No tool execution')):
                        terminal.input.text = '/new'
                        await terminal.submit()
                        new = terminal.store.session_id
                        self.assertNotEqual(old, new)
                        self.assertEqual(app.session_task.snapshot()['session_id'], new)
                        self.assertEqual(app.session_task.snapshot()['goal'], '')
                        terminal.input.text = '/resume ' + old
                        await terminal.submit()
                    self.assertEqual(app.session_task.snapshot()['session_id'], old)
                    self.assertEqual(app.session_task.snapshot()['goal'], '原任务')
                    self.assertEqual(app.session_task.snapshot()['state'], 'needs_review')
                    self.assertEqual(app.session_task.snapshot()['plan'], ['检查状态'])
                    self.assertFalse(terminal.queue)
                finally:
                    terminal.store.close()
                    app.close()
