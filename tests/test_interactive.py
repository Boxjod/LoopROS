import asyncio
import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from terminal.app import App
from terminal.config import load_config
from terminal.interactive import Terminal
from terminal.llm import ChatAgent, read_stream
from terminal.media import attachment, dropped_paths, clipboard_image
from terminal.protocols import encode


class StreamTests(unittest.TestCase):
    def test_dropped_media_paths_and_clipboard(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'my image.png'
            path.write_bytes(b'\x89PNG\r\n\x1a\n')
            self.assertEqual(dropped_paths(path.as_uri()), [str(path)])
            self.assertEqual(dropped_paths('"' + str(path) + '"'), [str(path)])
            self.assertEqual(dropped_paths('explain ' + str(path)), [])
        with patch.dict('os.environ', {'DISPLAY': ':0', 'WAYLAND_DISPLAY': ''}), patch('terminal.media.shutil.which', return_value='/usr/bin/xclip'), patch('terminal.media.subprocess.Popen') as spawn:
            process = spawn.return_value
            process.stdout = io.BytesIO(b'\x89PNG\r\n\x1a\nexample')
            process.wait.return_value = 0
            self.assertTrue(clipboard_image()[0]['image_url']['url'].startswith('data:image/png;base64,'))
            process.stdout = io.BytesIO(b'plain text')
            with self.assertRaisesRegex(ValueError, 'No PNG'):
                clipboard_image()

    def test_stream_fragments_and_tool_arguments(self):
        chunks = [{'choices': [{'delta': d}]} for d in [
            {'reasoning_content': 'check'}, {'content': 'hello'},
            {'tool_calls': [{'index': 0, 'id': 'a', 'function': {'name': 'status', 'arguments': '{'}}]},
            {'tool_calls': [{'index': 0, 'function': {'arguments': '}'}}]}]]
        chunks.append({'choices': [{'delta': {}, 'finish_reason': 'tool_calls'}]})
        payload = b''.join(b'data: ' + json.dumps(c).encode() + b'\n\n' for c in chunks) + b'data: [DONE]\n'
        events = []
        result = read_stream(io.BytesIO(payload), lambda *e: events.append(e))
        self.assertEqual(result['tool_calls'][0]['function']['arguments'], '{}')
        self.assertEqual(events, [('reasoning_delta', 'check'), ('answer_delta', 'hello')])

    def test_truncated_and_cancelled_streams(self):
        with self.assertRaises(RuntimeError):
            read_stream(io.BytesIO(b''), lambda *e: None)
        stop = threading.Event(); stop.set()
        with self.assertRaisesRegex(RuntimeError, 'stopped'):
            read_stream(io.BytesIO(b'data: [DONE]\n'), lambda *e: None, stop)

    def test_cancel_between_tools(self):
        stop = threading.Event()
        class Client:
            def complete(self, *args):
                return {'tool_calls': [{'id': str(i), 'function': {'name': 'status', 'arguments': '{}'}} for i in range(2)]}
        calls = []
        def dispatch(*args):
            calls.append(args); stop.set(); return {}
        agent = ChatAgent(Client(), [], dispatch, stop_event=stop)
        with self.assertRaisesRegex(RuntimeError, 'stopped'):
            agent.reply('test')
        self.assertEqual(len(calls), 1)
        self.assertEqual(agent.history, [])

    def test_media_protocols(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'image.png'
            path.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j4xkAAAAASUVORK5CYII='))
            parts = attachment(path)
        msg = [{'role': 'user', 'content': [{'type': 'text', 'text': 'look'}, *parts]}]
        _, body = encode({'protocol': 'responses', 'model': 'vision'}, msg, [])
        self.assertEqual(body['input'][0]['content'][1]['type'], 'input_image')
        self.assertTrue(body['input'][0]['content'][1]['image_url'].startswith('data:image/png;base64,'))

    def test_attachment_survives_followup_context(self):
        class Client:
            def __init__(self): self.messages = []
            def complete(self, messages, tools):
                self.messages = messages
                return {"content": "seen"}
        client = Client()
        agent = ChatAgent(client, [], lambda *args: None)
        media = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 32000}}
        agent.reply("look", [media])
        agent.reply("what color?")
        self.assertEqual(next(m for m in client.messages if m["role"] == "user")["content"][1], media)

    def test_http_stream_transport(self):
        from terminal.llm import QwenClient
        client = QwenClient(load_config()["llm"])
        client.key = "test-only"
        stream = io.BytesIO(b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n')
        events = []
        with patch("terminal.llm.build_opener") as opener:
            opener.return_value.open.return_value = stream
            result = client.complete([], [], on_event=lambda *e: events.append(e))
            self.assertTrue(json.loads(opener.return_value.open.call_args.args[0].data)["stream"])
        self.assertEqual(result["content"], "ok")
        self.assertEqual(events, [("answer_delta", "ok")])


class InteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_permission_menu_selects_rule_and_action(self):
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(d))
                terminal = Terminal(app)
                task = asyncio.create_task(terminal.run())
                try:
                    await asyncio.sleep(.2)
                    pipe.send_text('/permissions\r')
                    await asyncio.sleep(.3)
                    self.assertEqual(terminal.input.text, '/permissions ')
                    self.assertEqual(terminal.action_panel[0], '/permissions')
                    self.assertIn('Mode: sim', terminal.action_panel[1])
                    self.assertEqual(app.agent.history, [])
                    pipe.send_text('deny\r')
                    await asyncio.sleep(.2)
                    self.assertEqual(terminal.input.text, '/permissions deny ')
                    self.assertEqual(app.permissions.snapshot()['rules']['web_search'], 'allow')
                    pipe.send_text('web_s\r')
                    await asyncio.sleep(.3)
                    self.assertEqual(app.permissions.snapshot()['rules']['web_search'], 'deny')
                    self.assertEqual(terminal.input.text, '')
                    pipe.send_text('\x03')
                    await asyncio.wait_for(task, 3)
                finally:
                    if not task.done():
                        terminal.ui.exit()
                        await task
                    app.close()

    async def test_stream_error_allows_next_message_without_queue_resume(self):
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(d))
                terminal = Terminal(app)
                task = asyncio.create_task(terminal.run())
                try:
                    with patch.object(app.agent, 'reply', side_effect=[RuntimeError('stream interrupted'), 'recovered']) as reply:
                        await asyncio.sleep(.15)
                        pipe.send_text('hello\r')
                        await asyncio.sleep(.35)
                        self.assertIsNone(terminal.pending)
                        self.assertFalse(terminal.paused)
                        pipe.send_text('again\r')
                        await asyncio.sleep(.35)
                        self.assertEqual(reply.call_count, 2)
                        self.assertFalse(terminal.queue)
                        pipe.send_text('\x03')
                        await asyncio.wait_for(task, 3)
                finally:
                    if not task.done():
                        terminal.ui.exit()
                        await task
                    app.close()

    async def test_slash_completion_enter_runs_prefix_or_selected_command(self):
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(d))
                terminal = Terminal(app)
                task = asyncio.create_task(terminal.run())
                try:
                    with patch.object(app, 'dispatch', return_value='ok') as dispatch:
                        await asyncio.sleep(.2)
                        pipe.send_text('/per\r')
                        await asyncio.sleep(.3)
                        dispatch.assert_called_with('/permissions')
                        pipe.send_text('\x03/s')
                        await asyncio.sleep(.2)
                        pipe.send_text('\x1b[B')
                        await asyncio.sleep(.1)
                        selected = terminal.input.buffer.complete_state.current_completion.text
                        pipe.send_text('\r')
                        await asyncio.sleep(.3)
                        dispatch.assert_called_with(selected)
                        self.assertEqual(terminal.input.text, '')
                        pipe.send_text('\x03')
                        await asyncio.wait_for(task, 3)
                finally:
                    if not task.done():
                        terminal.ui.exit()
                        await task
                    app.close()

    async def test_up_retrieves_queued_message_with_attachments(self):
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(d))
                terminal = Terminal(app)
                terminal.paused = True
                files = [('image.png', [{'type': 'text', 'text': 'media fixture'}])]
                terminal.queue.extend([('first', []), ('你好', files)])
                task = asyncio.create_task(terminal.run())
                try:
                    await asyncio.sleep(.2)
                    pipe.send_text('\x1b[A')
                    await asyncio.sleep(.2)
                    self.assertEqual(terminal.input.text, '你好')
                    self.assertEqual(terminal.attachments, files)
                    self.assertEqual(list(terminal.queue), [('first', [])])
                    pipe.send_text('修改\r')
                    await asyncio.sleep(.25)
                    self.assertEqual(list(terminal.queue), [('first', []), ('你好修改', files)])
                    self.assertEqual(terminal.attachments, [])
                    terminal.command_busy = True
                    terminal.paused = False
                    pipe.send_text('\x03')
                    await asyncio.sleep(.15)
                    self.assertTrue(terminal.paused)
                    self.assertTrue(app.stop_event.is_set())
                    self.assertEqual(len(terminal.queue), 2)
                    terminal.command_busy = False
                    pipe.send_text('\x03')
                    await asyncio.wait_for(task, 3)
                finally:
                    if not task.done():
                        terminal.ui.exit()
                        await task
                    app.close()

    async def test_media_conversion_preserves_next_draft_and_queue(self):
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(d))
                terminal = Terminal(app)
                terminal.aliases = {}
                started = threading.Event()
                release = threading.Event()
                parts = [{'type': 'text', 'text': 'video frames'}]
                def convert(path):
                    started.set()
                    release.wait(3)
                    return parts
                try:
                    terminal.input.text = '/attach "clip.mp4"'
                    with patch('terminal.interactive.attachment', convert):
                        task = asyncio.create_task(terminal.submit())
                        for _ in range(50):
                            if started.is_set():
                                break
                            await asyncio.sleep(.01)
                        terminal.input.buffer.insert_text('解释视频')
                        release.set()
                        await task
                    self.assertEqual(terminal.input.text, '解释视频')
                    await terminal.submit()
                    self.assertEqual(terminal.queue[0], ('解释视频', [('clip.mp4', parts)]))
                    self.assertEqual(terminal.attachments, [])
                finally:
                    release.set()
                    terminal.store.close()
                    app.close()

    async def test_edit_queue_cancel_resume_and_background_output(self):
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(d))
                terminal = Terminal(app)
                entered = threading.Event(); release = threading.Event(); calls = []
                def reply(text, *args):
                    calls.append(text); entered.set(); release.wait(3)
                    if app.stop_event.is_set():
                        raise RuntimeError('Master stopped')
                    return 'done'
                app.agent.reply = reply
                task = asyncio.create_task(terminal.run())
                try:
                    await asyncio.sleep(.15)
                    # Real editor key sequences: move left and insert in middle.
                    pipe.send_text('ac\x1b[Db\r')
                    for _ in range(50):
                        if entered.is_set(): break
                        await asyncio.sleep(.02)
                    self.assertEqual(calls, ['abc'])
                    # Bracketed paste keeps embedded newlines in the composer.
                    pipe.send_text('\x1b[200~second\nline\x1b[201~')
                    await asyncio.sleep(.1)
                    self.assertEqual(terminal.input.text, 'second\nline')
                    pipe.send_text('\r')
                    await asyncio.sleep(.1)
                    self.assertEqual(len(terminal.queue), 1)
                    terminal.input.text = '/cancel-turn'
                    await terminal.submit()
                    await asyncio.sleep(.1)
                    self.assertTrue(terminal.paused)
                    release.set()
                    await asyncio.sleep(.2)
                    self.assertEqual(calls, ['abc'])
                    terminal.input.text = '/queue resume'
                    await terminal.submit()
                    await asyncio.sleep(.25)
                    self.assertEqual(calls, ['abc', 'second\nline'])
                    self.assertFalse(terminal.ui.full_screen)
                    self.assertFalse(terminal.ui.mouse_support())
                    terminal.input.text = 'draft'
                    terminal.append('test', 'another update')
                    self.assertEqual(terminal.input.text, 'draft')
                finally:
                    release.set()
                    terminal.ui.exit()
                    await asyncio.wait_for(task, 5)
                    app.close()

    async def test_invalid_attachment_retains_input(self):
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(d))
                try:
                    terminal = Terminal(app)
                    terminal.aliases = {}
                    terminal.input.text = '/attach /missing/not-a-file.png'
                    await terminal.submit()
                    self.assertEqual(terminal.input.text, '/attach /missing/not-a-file.png')
                    self.assertEqual(terminal.attachments, [])
                    terminal.store.close()
                finally:
                    app.close()

    async def test_ctrl_c_clear_then_exit_preserves_session(self):
        from terminal.session import SessionStore
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(d))
                terminal = Terminal(app)
                app.agent.history = [{'role': 'user', 'content': 'remember blue'}, {'role': 'assistant', 'content': 'blue'}]
                task = asyncio.create_task(terminal.run())
                try:
                    await asyncio.sleep(.1)
                    terminal.append('Master', 'blue')
                    pipe.send_text('draft\x03')
                    await asyncio.sleep(.15)
                    self.assertFalse(task.done())
                    self.assertEqual(terminal.input.text, '')
                    pipe.send_text('\x03')
                    await asyncio.wait_for(task, 5)
                    store = SessionStore(Path(d) / 'conversation.sqlite')
                    self.assertEqual(store.load(app.client.config)['history'], app.agent.history)
                    self.assertEqual(store.db.execute('SELECT text FROM transcript WHERE kind=?', ('Master',)).fetchone()[0], 'blue')
                    self.assertEqual((Path(d) / 'conversation.sqlite').stat().st_mode & 0o777, 0o600)
                    other = dict(app.client.config, base_url='https://different.example/v1')
                    self.assertEqual(store.load(other), {})
                    store.close()
                    restored = Terminal(app)
                    self.assertEqual(restored.app.agent.history[-1]['content'], 'blue')
                    restored.store.close()
                finally:
                    if not task.done():
                        terminal.ui.exit()
                        await task
                    app.close()

    async def test_chinese_stream_never_flushes_partial_stdout_line(self):
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(d))
                terminal = Terminal(app)
                terminal.aliases = {}
                try:
                    terminal.input.text = '草稿ac'
                    terminal.input.buffer.cursor_position = len(terminal.input.text)
                    terminal.input.buffer.cursor_left()
                    captured = io.StringIO()
                    with patch('sys.stdout', captured):
                        terminal.append('answer_delta', '调用相应')
                        terminal.append('answer_delta', '工具或委派子任务。')
                        self.assertEqual(captured.getvalue(), '')
                        self.assertIn('调用相应工具或委派子任务。', ''.join(t for _, t in terminal.prompt_text()))
                        terminal.input.buffer.insert_text('b')
                        self.assertEqual(terminal.input.text, '草稿abc')
                        terminal.append('You (queued)', '11')
                        import re
                        rendered = captured.getvalue()
                        self.assertEqual(re.sub(r'\x1b\[[0-9;]*m', '', rendered), '● 调用相应工具或委派子任务。\n❯ 11 (queued)\n')
                        self.assertTrue(rendered.endswith('\x1b[0m\n'))
                        terminal.append('answer_delta', '第一行\n第二')
                        terminal.append('answer_delta', '行')
                        terminal.flush_stream()
                        self.assertTrue(captured.getvalue().endswith('● 第一行\n  第二行\n'))
                        self.assertEqual(terminal.stream_text, '')
                        self.assertEqual(terminal.input.text, '草稿abc')
                        captured.seek(0)
                        captured.truncate()
                        terminal.append('answer_delta', '可用能力：\n\n- 状态查询\n')
                        terminal.append('answer_delta', '- 仿真控制\n\n完成。')
                        terminal.flush_stream()
                        terminal.append('tool', 'status({})')
                        terminal.append('result', '{"ready": true}')
                        self.assertTrue(captured.getvalue().startswith(
                                         '● 可用能力：\n\n  - 状态查询\n  - 仿真控制\n\n  完成。\n'
                                         'Tool › status({})\n  ↳ Returned data'))
                        self.assertRegex(captured.getvalue(), r'/details \d+\n$')
                        self.assertNotIn('{"ready": true}', captured.getvalue())

                finally:
                    terminal.store.close()
                    app.close()

class ResumeInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_selection_restores_context_and_continues_chat(self):
        with tempfile.TemporaryDirectory() as directory, create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), directory)
                terminal = Terminal(app)
                app.agent.history = [{'role':'user', 'content':'之前讨论电机'}, {'role':'assistant', 'content':'记录已保存'}]
                terminal.checkpoint()
                target = terminal.store.session_id
                terminal.store.new_session()
                app.agent.history = []
                terminal.checkpoint()
                task = asyncio.create_task(terminal.run())
                seen = []
                def reply(text):
                    seen.append((text, list(app.agent.history)))
                    return '继续讨论电机'
                try:
                    with patch.object(app.agent, 'reply', side_effect=reply):
                        await asyncio.sleep(.2)
                        pipe.send_text('/resume\r')
                        await asyncio.sleep(.3)
                        self.assertEqual(terminal.input.buffer.cursor_position, len('/resume '))
                        state = terminal.input.buffer.complete_state
                        self.assertIsNotNone(state)
                        for _ in range(len(state.completions)):
                            pipe.send_text('\x1b[B')
                            await asyncio.sleep(.06)
                            if terminal.store.resolve(app.client.config, terminal.input.buffer.complete_state.current_completion.text) == target:
                                break
                        pipe.send_text('\r')
                        await asyncio.sleep(.3)
                        self.assertEqual(terminal.store.session_id, target)
                        self.assertEqual(terminal.input.text, '')
                        pipe.send_text('继续\r')
                        await asyncio.sleep(.35)
                        self.assertEqual(seen[0][0], '继续')
                        self.assertEqual(seen[0][1][0]['content'], '之前讨论电机')
                        pipe.send_text('\x03')
                        await asyncio.wait_for(task, 3)
                finally:
                    if not task.done():
                        terminal.ui.exit()
                        await task
                    app.close()

    async def test_resume_browses_without_running_queue_and_restores_history(self):
        from terminal.interactive import Terminal
        with tempfile.TemporaryDirectory() as directory, create_pipe_input() as pipe:
            with create_app_session(input=pipe,output=DummyOutput()):
                app=App(load_config(),directory)
                terminal=Terminal(app)
                from terminal.app import ALIASES
                terminal.aliases=ALIASES
                try:
                    app.agent.history=[{'role':'user','content':'衣柜'}]
                    terminal.checkpoint();first=terminal.store.session_id
                    terminal.input.text='/new';await terminal.submit()
                    self.assertEqual(app.agent.history,[])
                    terminal.input.text='/resume '+first;await terminal.submit()
                    self.assertEqual(app.agent.history[0]['content'],'衣柜')
                    terminal.queue.append(('queued',[]));terminal.paused=True
                    terminal.input.text='/resume'
                    with patch.object(terminal.input.buffer, 'start_completion') as start_completion:
                        await terminal.submit()
                        start_completion.assert_not_called()
                    self.assertTrue(terminal.paused)
                    self.assertEqual(len(terminal.queue),1)
                    terminal.input.buffer.cancel_completion()
                finally:
                    terminal.store.close();app.close()
