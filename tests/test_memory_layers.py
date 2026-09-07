import json
from pathlib import Path
import tempfile
import unittest
from loop_robot.terminal.learning import Learning


class MemoryLayerTests(unittest.TestCase):
    def test_quoted_assistant_preferences_are_not_user_memory(self):
        from loop_robot.terminal.memory_facts import extract
        for text in ('> 记住默认播放五条轨迹', '助手：记住默认播放五条轨迹',
                     '他说“记住默认播放五条轨迹”是什么意思',
                     'Tools ▸ read_file\n● 记住默认播放五条轨迹'):
            self.assertEqual(extract(text), [], text)
        memory=extract('记住默认使用中文')[0]
        self.assertEqual(memory['source_role'],'user')
        self.assertEqual(memory['evidence'],'user_statement_not_verified')

    def test_unknown_or_conflicting_source_is_available_for_audit_not_auto_recall(self):
        for payload in ({'evidence':'user_statement_not_verified'},
                        {'evidence':'user_statement_not_verified','source_role':'assistant'}):
            identity=self.learning.layers.save('scope','detail',str(payload),'独角兽偏好',payload,'old-source')
            item=self.learning.layers.read('scope',identity)
            self.assertEqual(item['provenance']['review_status'],'review_required')
        self.assertEqual(self.learning.context('独角兽偏好'),'')

    def test_user_and_tool_detail_do_not_overwrite_each_other(self):
        from loop_robot.terminal.memory_facts import extract
        user=extract('记住地址192.168.1.19')[0]
        observation={**user,'kind':'connection_observation','source_role':'tool',
                     'evidence':'historical_tool_observation_not_current_state'}
        self.learning.retain('user-source',[user])
        self.learning.retain('tool-source',[observation])
        rows=self.learning.layers.search('scope','192.168.1.19')
        self.assertEqual({r['provenance']['source_role'] for r in rows},{'user','tool'})
        self.assertTrue(all(r['provenance']['authority']=='historical_data_only' for r in rows))

    def test_unattributed_detail_is_rejected_at_retention(self):
        self.learning.retain('unknown',[{'text':'无来源偏好','evidence':'user_statement_not_verified'}])
        self.assertEqual(self.learning.layers.search('scope','无来源偏好'),[])

    def test_source_linked_assistant_note_stays_unverified(self):
        source=self.learning.record_turn({'request':'记住默认使用中文'},[])
        note=self.learning.store.revise('scope','language','建议使用中文',[source],0)
        self.assertEqual(note['source_role'],'assistant')
        self.assertEqual(note['review_status'],'advisory_not_verified')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.learning = Learning(Path(self.tmp.name) / 'learning.sqlite', lambda: 'scope')

    def test_correction_is_recalled_without_promoting_success(self):
        self.learning.record_turn({'request':'启动机器人太浪费时间，不要再重复读取全部脚本'}, [], session_id='corrected')
        matches = self.learning.layers.search('scope', '启动机器人')
        correction = next(m for m in matches if m['payload'].get('category') == 'correction')
        self.assertEqual(correction['payload']['priority'], 'high')
        self.assertEqual(correction['payload']['evidence'], 'user_feedback_signal_not_execution_evidence')
        self.assertTrue(correction['sources'])
        self.learning.record_turn({'request':'好的'}, [])
        self.assertFalse(any(m['kind'] in ('last_success','procedure') for m in self.learning.layers.search('scope','启动机器人')))

    def test_quoted_feedback_does_not_become_direct_complaint(self):
        from loop_robot.terminal.memory_facts import extract
        memories = extract('例子：\n```text\n太慢了，不要再重复\n```\n> 你到底会不会')
        self.assertFalse(any(m.get('category') == 'correction' for m in memories))

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
