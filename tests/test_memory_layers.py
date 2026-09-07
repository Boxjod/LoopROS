import json
from pathlib import Path
import tempfile
import unittest
from terminal.learning import Learning


class MemoryLayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.learning = Learning(Path(self.tmp.name) / 'learning.sqlite', lambda: 'scope')

    def test_old_auth_and_preferences_survive_recent_task_noise(self):
        self.learning.record_turn({'request': 'Jetson 用户名 jetson。可以 ssh 免密连接'}, [], session_id='old')
        self.learning.record_turn({'request': '我喜欢简短的中文回复，机器人操作习惯先读取状态'}, [])
        for i in range(30):
            self.learning.record_turn({'request': '连接 Jetson 192.168.1.' + str(i + 1)}, [], task_id=str(i),
                                      task={'goal': '连接 Jetson', 'state': 'waiting_input'})
        context = self.learning.context('开启任务连接 Jetson 192.168.19.1')
        self.assertIn('用户名 jetson', context)
        self.assertIn('免密', context)
        self.assertIn('Current explicit parameters override old defaults', context)
        self.assertIn('do not ask again', context)
        self.assertNotIn('用户名 jetson', self.learning.context('今天气温如何'))
        self.assertIn('简短的中文', self.learning.context('我的回复习惯'))
        block = context.split('):\n', 1)[1].split('\nReuse known', 1)[0]
        self.assertLessEqual(len(block), 3000)

    def test_summary_keeps_goal_and_refs_separate_from_details(self):
        identity = self.learning.record_turn({'request': '下一步检查状态'}, [], session_id='s', task_id='t',
                           task={'goal': '检查 Jetson 运行时', 'state': 'waiting_input', 'next_step': '等待网络恢复'})
        records = self.learning.layers.search('scope', 'Jetson')
        summary = next(row for row in records if row['kind'] == 'summary')
        self.assertIn(identity, summary['sources'])
        self.assertEqual(summary['payload']['task_id'], 't')
        self.assertEqual(summary['payload']['session_id'], 's')
        self.assertEqual(summary['payload']['next_step'], '等待网络恢复')
        self.assertEqual(self.learning.layers.search('other', 'Jetson'), [])

    def task(self, identity, ok=True, target='jetson'):
        return {'id': identity, 'attempt': 1, 'state': 'succeeded' if ok else 'waiting_input',
                'spec': {'goal': '只读核对 Jetson 状态', 'checks': [{'tool': 'observe', 'path': 'ok', 'equals': True}]},
                'feedback': {'worker_state': 'done', 'receipts': [
                    {'tool': 'observe', 'arguments': {'target': target}, 'result': {'ok': ok}}]}}

    def procedures(self):
        return [row for row in self.learning.layers.search('scope', 'Jetson', 10) if row['kind'] == 'procedure']

    def test_three_independent_verified_runs_promote_not_retries(self):
        one = self.task('one')
        for i in range(1, 5):
            one['attempt'] = i
            self.learning.record_task(one)
        self.assertEqual(self.procedures(), [])
        self.learning.record_task(self.task('two'))
        self.assertEqual(self.procedures(), [])
        self.learning.record_task(self.task('three'))
        recipe = self.procedures()[0]
        self.assertEqual(recipe['payload']['verified_runs'], 3)
        self.assertEqual(len(recipe['sources']), 3)
        self.assertEqual(recipe['payload']['steps'], [{'tool': 'observe', 'arguments': {'target': 'jetson'}}])
        self.learning.record_task(self.task('four', ok=False))
        self.assertEqual(self.procedures(), [])

    def test_different_parameters_and_prose_success_do_not_promote(self):
        for i in range(3):
            self.learning.record_task(self.task(str(i), target='host-' + str(i)))
        self.assertEqual(self.procedures(), [])

        for i in range(3):
            task = self.task('fake-' + str(i), ok=False)
            task['state'] = 'succeeded'
            task['feedback']['worker_result'] = 'Successfully connected'
            self.learning.record_task(task)
        self.assertEqual(self.procedures(), [])

    def test_foreground_procedure_requires_actual_checks_and_three_tasks(self):
        events = [('tool', 'observe({"target":"jetson"})'), ('result', '{"ok":true}')]
        task = {'goal': '检查 Jetson 状态', 'state': 'complete',
                'checks': [{'tool': 'observe', 'path': 'ok', 'equals': True}]}
        for i in range(3):
            self.learning.record_turn({'request': '检查 Jetson'}, events, task_id='front-' + str(i), task=task)
        self.assertEqual(self.procedures()[0]['payload']['verified_runs'], 3)

    def test_old_user_experience_is_imported_once_without_new_authority(self):
        identity = self.learning.store.record('scope', 'turn:old', 'Jetson 用户名 jetson，SSH 免密连接', 'observed',
                                               {'observations': [], 'session_id': 'old'})
        context = self.learning.context('连接 Jetson')
        self.assertIn('免密', context)
        self.assertIn(identity, context)
        self.assertIn('user_statement_not_verified', context)
        reopened = Learning(self.learning.path, lambda: 'scope')
        self.assertEqual(len([r for r in reopened.layers.search('scope', 'Jetson') if r['kind'] == 'detail']), 1)
