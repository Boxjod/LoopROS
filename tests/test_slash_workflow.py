import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prompt_toolkit.application import create_app_session
from prompt_toolkit.document import Document
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from terminal.app import App, HELP
from terminal.config import load_config
from terminal.completion import SlashCompleter
from terminal.interactive import Terminal


class SlashWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_stream_records_tier_without_changing_text(self):
        import io
        from terminal.llm import read_stream
        tiers = []
        result = read_stream(io.BytesIO(b'data: {"service_tier":"priority","choices":[{"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n'),
                             lambda *args: None, on_tier=tiers.append)
        self.assertEqual(tiers, ['priority'])
        self.assertEqual(result['content'], 'OK')

    def test_menu_order_mode_and_hidden_history(self):
        menu = SlashCompleter(HELP)
        def choices(text):
            return [c.text for c in menu.get_completions(Document(text), CompleteEvent())]
        self.assertEqual(choices('/')[:5], ['/model','/mode','/permissions','/resume','/help'])
        self.assertNotIn('/history', choices('/'))
        self.assertIn('/history', choices('/hist'))
        self.assertEqual(choices('/mode '), ['sim','real','plan'])
        self.assertIn('/fast', choices('/f'))
        self.assertEqual(choices('中1'), [])

    async def test_catalog_selection_fast_and_chinese_after_menu(self):
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe, patch.dict('os.environ', {'LOOP_HOME':d+'/home','LOOP_TASK_AUTOSTART':'0'}):
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(d)/'state')
                app.client.key = 'fixture-key'
                terminal = Terminal(app)
                rows = [{'id':'model-a','company':'A','date':'2026-09-01'}, {'id':'model-b','company':'B','date':'Unknown'}]
                received = []
                def reply(text, *args):
                    received.append(text)
                    return 'OK'
                app.agent.reply = reply
                with patch('terminal.setup.discover_models', return_value=rows) as discover:
                    task = asyncio.create_task(terminal.run())
                    try:
                        await asyncio.sleep(.2)
                        pipe.send_text('/model\r')
                        await asyncio.sleep(.3)
                        self.assertEqual(terminal.input.text, '/model ')
                        discover.assert_called_once()
                        self.assertEqual(discover.call_args.args[0]['base_url'], app.client.config['base_url'])
                        pipe.send_text('model-b\r')
                        await asyncio.sleep(.3)
                        self.assertEqual(app.client.config['model'],'model-b')
                        pipe.send_text('/fast\r')
                        await asyncio.sleep(.3)
                        self.assertEqual(app.client.request_service_tier, 'priority')
                        pipe.send_text('/fast off\r')
                        await asyncio.sleep(.3)
                        self.assertEqual(app.client.request_service_tier, 'default')
                        pipe.send_text('/')
                        await asyncio.sleep(.15)
                        pipe.send_text('\x7f中1')
                        await asyncio.sleep(.2)
                        self.assertEqual(terminal.input.text,'中1')
                        self.assertIsNone(terminal.input.buffer.complete_state)
                        pipe.send_text('\r')
                        await asyncio.sleep(.4)
                        self.assertEqual(received, ['中1'])
                        pipe.send_text('/exit\r')
                        await asyncio.wait_for(task,3)
                    finally:
                        if not task.done():
                            terminal.ui.exit()
                            await task
                        app.close()
