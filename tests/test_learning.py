import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from core.experience import ExperienceStore
from core.tasks import TaskStore
from terminal.learning import Learning
from terminal.task_supervisor import TaskSupervisor


def recall_worker(pipe, definition, config, key, task, schemas):
    data = json.loads(task)
    recalled = 'historical experience' in data.get('related_experience', '')
    pipe.send({'type': 'tool', 'name': 'observe', 'arguments': {'value': recalled}})
    pipe.recv()
    pipe.send({'type': 'result', 'result': 'Observed'})
    pipe.close()


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = ExperienceStore(self.path / 'learning.sqlite')
        self.learning = Learning(self.store.path, lambda: 'workspace-A', secrets=lambda: ['configured-private-key'])

    def tearDown(self):
        self.temp.cleanup()

    def record(self, scope='workspace-A', origin='first', request='检查串口连接 motor serial'):
        return self.store.record(scope, origin, request, 'observed', {'observations': [], 'skills_read': []})

    def test_persistent_scoped_bilingual_recall_dedup_and_newest_ties(self):
        identity = self.record()
        self.assertEqual(self.record(), identity)
        self.record('workspace-B', 'other')
        reopened = ExperienceStore(self.store.path)
        self.assertEqual(reopened.search('workspace-A', '串口连接')[0]['id'], identity)
        self.assertEqual(reopened.search('workspace-A', 'motor serial')[0]['id'], identity)
        self.assertEqual(reopened.search('workspace-A', 'weather forecast'), [])
        with self.assertRaises(ValueError): reopened.read('workspace-B', identity)
        for i in range(110):
            latest = self.record(origin='repeat-' + str(i))
        self.assertEqual(reopened.search('workspace-A', 'motor serial', 1)[0]['id'], latest)

    def test_note_sources_revision_conflicts_forget_and_restore(self):
        identity = self.record()
        first = self.store.revise('workspace-A', 'serial-check', 'Check serial connection first.', [identity], 0)
        self.assertEqual(first['status'], 'advisory_unverified')
        with self.assertRaises(ValueError): self.store.revise('workspace-A', 'serial-check', 'Overwrite', [identity], 0)
        with self.assertRaises(ValueError): self.store.revise('workspace-B', 'serial-check', 'Cross scope', [identity], 0)
        second = self.store.revise('workspace-A', 'serial-check', 'Check baud rate too.', [identity], 1)
        self.assertEqual(second['revision'], 2)
        self.assertEqual(self.store.lesson('workspace-A', 'serial-check', 1)['content'], first['content'])
        self.store.revise('workspace-A', 'serial-check', second['content'], [identity], 2, active=False)
        self.assertFalse(any(r['kind'] == 'lesson' for r in self.store.search('workspace-A', 'motor serial')))
        restored = self.store.revise('workspace-A', 'serial-check', first['content'], [identity], 3)
        self.assertEqual(restored['revision'], 4)
        self.assertTrue(restored['active'])

    def test_tool_evidence_redaction_skill_version_and_cancellation(self):
        events = [('tool', 'skill_read({"name":"serial-check"})'),
                  ('result', json.dumps({'name': 'serial-check', 'sha256': 'v1', 'content': 'private file body'})),
                  ('tool', 'read_file({})'),
                  ('result', json.dumps({'error': 'ValueError', 'message': 'configured-private-key password=hidden', 'content': 'private body'}))]
        summary = {'request': 'motor serial configured-private-key', 'error': None, 'answer_excerpt': 'ALL VERIFIED'}
        identity = self.learning.record_turn(summary, events)
        record = self.store.read('workspace-A', identity)
        self.assertEqual(record['outcome'], 'error')
        self.assertEqual(record['payload']['skills_read'], [{'name': 'serial-check', 'sha256': 'v1'}])
        usage = self.store.skill_usage('workspace-A', 'serial-check')['versions'][0]
        self.assertEqual(usage, {'sha256': 'v1', 'reads': 1, 'turns_with_errors': 1, 'verified_tasks': 0})
        encoded = json.dumps(record)
        for secret in ('configured-private-key', 'hidden', 'private body', 'private file body', 'ALL VERIFIED'):
            self.assertNotIn(secret, encoded)
        cancelled = self.learning.record_turn(summary, events, cancelled=True)
        self.assertEqual(self.store.read('workspace-A', cancelled)['outcome'], 'cancelled')
        self.assertIsNone(self.learning.record_turn(summary, []))
        self.assertLess(len(self.learning.context('motor serial')), 6000)

    def test_task_verification_rechecks_receipts_and_never_trusts_prose(self):
        task = {'id': 'task1', 'attempt': 1, 'state': 'succeeded',
                'spec': {'goal': 'motor serial', 'checks': [{'tool': 'observe', 'path': 'ok', 'equals': True}]},
                'feedback': {'worker_state': 'done', 'worker_result': 'success', 'review': {'verdict': 'pass'},
                             'receipts': [{'tool': 'observe', 'result': {'ok': False}}]}}
        identity = self.learning.record_task(task)
        self.assertEqual(self.store.read('workspace-A', identity)['outcome'], 'inconclusive')
        task['attempt'] = 2
        task['feedback']['receipts'][0]['result']['ok'] = True
        identity = self.learning.record_task(task)
        self.assertEqual(self.store.read('workspace-A', identity)['outcome'], 'verified')
        self.assertEqual(self.learning.record_task(task), identity)
        task['attempt'] = 3
        task['state'] = 'cancelled'
        identity = self.learning.record_task(task)
        self.assertEqual(self.store.read('workspace-A', identity)['outcome'], 'cancelled')

    def test_connection_hint_without_tools_survives_session_change(self):
        identity = self.learning.record_turn({'request': 'Jetson 使用 ssh jetson@192.168.1.19 -p 22，通过现有 SSH 密钥连接'}, [], session_id='session-one')
        reopened = Learning(self.store.path, lambda: 'workspace-A')
        context = reopened.context('Jetson 的运行时怎么查看')
        for value in (identity, '192.168.1.19', 'ssh', 'session-one', 'user_statement_not_verified'):
            self.assertIn(value, context)
        self.assertEqual(reopened.context('今天的天气如何'), '')
        self.assertIn('192.168.1.19', reopened.context('上次机器人的连接方式'))
        self.assertEqual(Learning(self.store.path, lambda: 'workspace-B').context('Jetson 地址'), '')
        self.assertIsNone(reopened.record_turn({'request': '好的谢谢'}, []))

    def test_connection_correction_keeps_sources_and_budget(self):
        for address in ('192.168.1.19', '192.168.1.20'):
            self.learning.record_turn({'request': '记住 Jetson 地址 ' + address + '，ssh 连接'}, [])
        context = self.learning.context('Jetson 地址')
        self.assertIn('192.168.1.19', context)
        self.assertIn('192.168.1.20', context)
        self.assertLess(context.index('192.168.1.20'), context.index('192.168.1.19'))
        self.assertLess(len(context), 4200)
        self.learning.record_turn({'request': '记住 Jetson 地址 192.168.1.20，ssh 连接'}, [])
        context = self.learning.context('Jetson 地址')
        self.assertEqual(context.count('user_statement_not_verified'), 2)

    def test_memory_redacts_credentials_and_never_learns_assistant_claim(self):
        identity = self.learning.record_turn({'request': '记住 Jetson 192.168.1.19 密码：hidden https://user:pass@example.com configured-private-key',
                                              'answer_excerpt': 'SSH succeeded and robot is online'}, [])
        data = json.dumps(self.store.read('workspace-A', identity), ensure_ascii=False)
        for secret in ('hidden', 'user:pass', 'configured-private-key', 'SSH succeeded'):
            self.assertNotIn(secret, data)
        self.assertIn('user_statement_not_verified', data)

    def test_structured_observation_tags_not_stdout_or_success_claims(self):
        events = [('tool', 'observe({})'), ('result', json.dumps({'connection': {'host': '192.168.1.19', 'transport': 'ssh', 'username': 'jetson'},
                   'stdout': 'password=private and connected successfully', 'ok': True}))]
        identity = self.learning.record_turn({'request': '查询 Jetson 连接信息'}, events)
        data = self.store.read('workspace-A', identity)
        self.assertEqual(data['outcome'], 'observed')
        self.assertEqual(data['payload']['memories'][0]['evidence'], 'historical_tool_observation_not_current_state')
        self.assertNotIn('private', json.dumps(data))
        self.assertIn('192.168.1.19', self.learning.context('Jetson 地址'))

    def test_background_worker_reuses_experience_then_records_verified_result(self):
        self.record(request='motor serial')
        store = TaskStore(self.path / 'tasks.sqlite')
        policy = {'max_workers': 1, 'attempt_timeout_s': 10, 'retry_initial_s': 1, 'retry_max_s': 2,
                  'stalled_attempts': 2, 'worker_tools': ['observe'], 'scheduled_tools': ['observe'],
                  'schedules': [], 'triggers': []}
        supervisor = TaskSupervisor(store, policy, {'llm': SimpleNamespace(config={}, key=None, resolved_key=lambda: None)}, [],
                                    lambda name, args: {'ok': args['value']}, self.path / 'agents.jsonl', [],
                                    worker_target=recall_worker, learning=self.learning)
        try:
            task = store.submit({'goal': 'motor serial', 'checks': [{'tool': 'observe', 'path': 'ok', 'equals': True}]})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                supervisor.poll()
                if store.get(task['id'])['state'] == 'succeeded': break
                time.sleep(.02)
            self.assertEqual(store.get(task['id'])['state'], 'succeeded')
            matches = self.learning.recall('motor serial')
            self.assertEqual(matches[0]['outcome'], 'verified')
        finally:
            supervisor.close()


class LearningAppTests(unittest.TestCase):
    def setUp(self):
        from terminal.app import App
        from terminal.config import load_config
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict('os.environ', {'LOOP_HOME': str(self.root / 'home'), 'LOOP_TASK_AUTOSTART': '0'})
        self.env.start()
        self.app = App(load_config(), self.root / 'state')
        self.app.workspace_root = self.root
        self.app.agent.on_turn_finished = None

    def tearDown(self):
        self.app.close()
        self.env.stop()
        self.temp.cleanup()

    def test_real_tool_turn_new_app_recall_and_model_note_revision(self):
        from terminal.app import App
        from terminal.config import load_config
        (self.root / 'example.txt').write_text('serial baud verification')
        call = {'id': 'read-1', 'type': 'function', 'function': {'name': 'read_file', 'arguments': json.dumps({'path': str(self.root / 'example.txt')})}}
        with patch.object(self.app.client, 'complete', side_effect=[{'content': '', 'tool_calls': [call]}, {'content': 'Read complete'}]):
            self.app.agent.reply('Read serial baud example.txt')
        identity = self.app.agent.turn_summaries[-1]['experience_id']
        self.app.close()
        self.app = App(load_config(), self.root / 'state')
        self.app.workspace_root = self.root
        self.app.agent.on_turn_finished = None
        seen = []
        def complete(messages, tools):
            seen.append(messages)
            if len(seen) == 1:
                self.assertIn(identity, messages[0]['content'])
                return {'content': '', 'tool_calls': [{'id': 'note-1', 'type': 'function', 'function': {'name': 'learning_note', 'arguments': json.dumps({
                    'name': 'serial-baud', 'content': 'Read the current serial baud configuration before diagnosing; verify against current device data.',
                    'source_ids': [identity], 'expected_revision': 0})}}]}
            return {'content': 'Saved advisory note'}
        with patch.object(self.app.client, 'complete', side_effect=complete):
            self.assertEqual(self.app.agent.reply('Review serial baud example.txt'), 'Saved advisory note')
        note = self.app.tool('experience_read', {'note': 'serial-baud'})
        self.assertEqual(note['revision'], 1)
        self.assertEqual(note['status'], 'advisory_unverified')
        self.assertIn('serial-baud', self.app.agent.context_provider('serial baud')['system_prompt'])
        self.app.tool('learning_forget', {'name': 'serial-baud', 'expected_revision': 1})
        self.assertFalse(self.app.tool('experience_read', {'note': 'serial-baud'})['active'])
        self.app.workspace_root = self.root / 'other'
        self.assertEqual(self.app.tool('experience_search', {'query': 'serial baud'})['matches'], [])

    def test_conversation_only_memory_is_available_to_next_session_model(self):
        from terminal.session_task import SessionTask
        self.app.session_task = SessionTask(identity='first-session')
        with patch.object(self.app.client, 'complete', return_value={'content': '已记录地址，尚未验证连接'}) as complete:
            self.app.agent.reply('记住 Jetson 使用 ssh jetson@192.168.1.19 -p 22')
            self.assertEqual(complete.call_count, 1)
        source = self.app.agent.turn_summaries[-1]['experience_id']
        record = self.app.learning.store.read(self.app.learning.scope(), source)
        self.assertEqual(record['payload']['session_id'], 'first-session')
        self.assertEqual(record['payload']['task_id'], self.app.session_task.data['id'])
        self.app.session_task = SessionTask(identity='second-session')
        self.app.agent.history = []
        self.app.agent.turn_summaries = []
        with patch.object(self.app.client, 'complete', return_value={'content': '历史记录中为该地址，需要确认当前状态'}) as complete:
            self.app.agent.reply('上次机器人的连接方式是什么')
            self.assertEqual(complete.call_count, 1)
            system = complete.call_args.args[0][0]['content']
            self.assertIn('192.168.1.19', system)
            self.assertIn('user_statement_not_verified', system)
            self.assertIn(source, system)

    def test_permission_gate_disables_recall_and_plan_blocks_note_changes(self):
        identity = self.app.learning.store.record(self.app.learning.scope(), 'test', 'serial baud', 'observed', {'observations': []})
        self.app.permissions.set_rule('experience_read', 'deny')
        self.assertNotIn(identity, self.app.agent.context_provider('serial baud')['system_prompt'])
        self.assertEqual(self.app.learning.context('serial baud', nudge=False), '')
        with self.assertRaises(PermissionError): self.app.tool('experience_read', {'id': identity})
        self.app.permissions.set_mode('plan')
        with self.assertRaises(PermissionError): self.app.tool('learning_note', {'name': 'test', 'content': 'test', 'source_ids': [identity], 'expected_revision': 0})

    def test_learning_failure_does_not_mask_completed_turn(self):
        with patch.object(self.app.client, 'complete', return_value={'content': 'Hello'}), patch.object(self.app.learning, 'record_turn', side_effect=OSError('disk error')):
            self.assertEqual(self.app.agent.reply('Hello'), 'Hello')
        self.assertEqual(self.app.agent.turn_summaries[-1]['learning_error'], 'OSError')
        with patch.object(self.app.learning, 'context', side_effect=OSError('disk error')):
            self.assertIn('recall is unavailable', self.app.agent.context_provider('hello')['system_prompt'])

    def test_skill_update_requires_fresh_hash_and_retains_backup(self):
        self.app.permissions.set_rule('skill_write', 'allow')
        args = {'name': 'learned-check', 'description': 'A test skill', 'content': 'Check and verify.'}
        self.app.tool('skill_write', args)
        old = self.app.tool('skill_read', {'name': args['name']})
        with self.assertRaises(ValueError): self.app.tool('skill_write', {**args, 'content': 'Overwrite unseen content'})
        result = self.app.tool('skill_write', {**args, 'content': 'Check current state then verify.', 'expected_sha256': old['sha256']})
        self.assertEqual(Path(result['backup']).read_text(), old['content'])
        with self.assertRaises(ValueError): self.app.tool('skill_write', {**args, 'expected_sha256': old['sha256']})

    def test_corrupt_learning_database_does_not_prevent_startup_or_chat(self):
        from terminal.app import App
        from terminal.config import load_config
        self.app.close()
        (self.root / 'state' / 'learning.sqlite').write_bytes(b'not a sqlite database')
        self.app = App(load_config(), self.root / 'state')
        self.app.workspace_root = self.root
        self.app.agent.on_turn_finished = None
        with patch.object(self.app.client, 'complete', return_value={'content': 'Still available'}):
            self.assertEqual(self.app.agent.reply('Hello again'), 'Still available')
        self.assertIn('recall is unavailable', self.app.agent.context_provider('hello')['system_prompt'])
