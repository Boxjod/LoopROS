import json
import tempfile
import unittest
from pathlib import Path
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from loop_robot.terminal.completion import SlashCompleter
from loop_robot.terminal.session import SessionStore
from loop_robot.terminal.titles import conversation_title, task_title
from loop_robot.terminal.command_display import format_command_result

CONFIG = {'base_url': 'https://example.invalid', 'model': 'test'}


class TitleTests(unittest.TestCase):
    def test_first_and_latest_questions_with_media_and_empty_input(self):
        history = [{'role':'user','content':'请帮我连接机器人'}, {'role':'assistant','content':'IGNORE THIS'},
                   {'role':'user','content':'配置串口'}, {'role':'user','content':'修复权限切换'}]
        title = conversation_title(history)
        self.assertEqual(title, '连接机器人 · 修复权限切换')
        self.assertNotIn('配置串口', title)
        self.assertEqual(conversation_title([]), 'New conversation')
        self.assertEqual(conversation_title([{'role':'user','content':[{'type':'text','text':'检查图片'}, {'type':'image_url','image_url':{'url':'private'}}]}]), '检查图片')
        self.assertEqual(task_title({'spec': {'goal':'检查电机'}, 'feedback':{'new_input':'核对波特率'}}), '检查电机 · 核对波特率')

    def test_titles_update_manual_names_duplicates_and_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(Path(directory) / 'sessions.sqlite')
            try:
                first = [{'role':'user','content':'连接机器人'}]
                store.save(CONFIG, first, [])
                original = store.session_id
                store.save(CONFIG, first + [{'role':'user','content':'修复权限切换'}], [])
                title = store.title(CONFIG)
                self.assertEqual(title, '连接机器人 · 修复权限切换')
                self.assertEqual(store.resume(CONFIG, title)['session_id'], original)
                store.new_session()
                store.save(CONFIG, first + [{'role':'user','content':'修复权限切换'}], [])
                rows = store.list_sessions(CONFIG)
                self.assertEqual(len({r['label'] for r in rows}), 2)
                with self.assertRaisesRegex(ValueError, 'Several conversations'):
                    store.resume(CONFIG, title)
                for row in rows:
                    resumed = store.resume(CONFIG, row['label'])
                    self.assertEqual(resumed['session_id'], row['id'])
                    store.save(CONFIG, resumed['history'], [])
                    self.assertEqual(store.resolve(CONFIG, row['label']), row['id'])
                store.rename(CONFIG, '我的机器人工作')
                store.save(CONFIG, first + [{'role':'user','content':'更新程序'}], [])
                self.assertEqual(store.title(CONFIG), '我的机器人工作')
                self.assertEqual(store.resolve(CONFIG, original), original)
            finally:
                store.close()

    def test_completion_and_task_display_use_titles_not_ids(self):
        rows = [{'id':'hidden-id', 'title':'连接机器人 · 修复权限切换', 'label':'连接机器人 · 修复权限切换', 'turns':2, 'updated':'today'}]
        completer = SlashCompleter('', sessions=lambda: rows)
        completions = list(completer.get_completions(Document('/resume 连接机器人 · 修'), CompleteEvent()))
        self.assertEqual(completions[0].text, rows[0]['label'])
        self.assertNotIn('hidden-id', str(completions[0].display))
        rendered = format_command_result('/tasks', {'task':[{'id':'hidden-id','session_id':'hidden-session','spec':{'goal':'检查机器人'}, 'state':'queued'}]})
        self.assertIn('检查机器人', rendered)
        self.assertNotIn('hidden-id', rendered)
        self.assertNotIn('hidden-session', rendered)

    def test_operator_task_commands_accept_readable_titles(self):
        import os
        from unittest.mock import patch
        from loop_robot.terminal.app import App
        from loop_robot.terminal.config import load_config
        from loop_robot.core.tasks import TaskStore
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOOP_HOME': directory + '/home'}):
            app = App(load_config(), Path(directory) / 'state')
            try:
                store = TaskStore(app.state_dir / 'tasks.sqlite')
                task = store.submit({'goal': 'Check robot connection', 'session_id': app.session_id})
                value = json.loads(app.dispatch('/tasks status Check robot connection'))
                self.assertEqual(value['task']['id'], task['id'])
                store.update(task['id'], 'waiting_input')
                with patch('loop_robot.terminal.task_service.start', return_value={}):
                    value = json.loads(app.dispatch('/tasks resume Check robot connection -- check serial port'))
                self.assertEqual(value['task']['feedback']['new_input'], 'check serial port')
                value = app.dispatch('/tasks cancel Check robot connection · check serial port')
                rendered = format_command_result('/tasks', value)
                self.assertIn('cancelled', rendered)
                self.assertNotIn(task['id'], rendered)
            finally:
                app.close()
