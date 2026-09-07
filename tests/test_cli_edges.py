import asyncio
from contextlib import asynccontextmanager
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

class CliEdges(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def terminal(self):
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as pipe, patch.dict('os.environ',{'LOOP_TASK_AUTOSTART':'0','LOOP_HOME':d+'/home'}):
            with create_app_session(input=pipe,output=DummyOutput()):
                app=App(load_config(),Path(d)/'state');terminal=Terminal(app)
                task=asyncio.create_task(terminal.run())
                try:
                    await asyncio.sleep(.15)
                    yield app,terminal,pipe
                finally:
                    if not task.done():terminal.ui.exit()
                    await asyncio.wait_for(task,5)
                    app.close()

    async def test_completion_refreshes_after_delete_paste_cursor_and_escape(self):
        async with self.terminal() as (app,t,pipe):
            with patch.object(app,'dispatch') as dispatch:
                def matches():
                    state=t.input.buffer.complete_state
                    return [c.text for c in state.completions] if state else []
                pipe.send_text('/sw');await asyncio.sleep(.2)
                self.assertEqual(matches(),['/switch'])
                pipe.send_text('\x7f');await asyncio.sleep(.2)
                self.assertIn('/status',matches())
                pipe.send_text('\x1b[H');await asyncio.sleep(.2)
                self.assertEqual(matches(),[])
                pipe.send_text('\x1b[F');await asyncio.sleep(.2)
                self.assertIn('/status',matches())
                pipe.send_text('\x1b');await asyncio.sleep(.65)
                self.assertEqual(matches(),[])
                await asyncio.sleep(.2);self.assertEqual(matches(),[])
                pipe.send_text('w');await asyncio.sleep(.2)
                self.assertEqual(matches(),['/switch'])
                pipe.send_text('\x03');await asyncio.sleep(.1)
                pipe.send_text('\x1b[200~/per\x1b[201~');await asyncio.sleep(.2)
                self.assertEqual(matches(),['/permissions'])
                dispatch.assert_not_called()

    async def test_attachment_only_turn_queues_without_index_error(self):
        async with self.terminal() as (app,t,pipe):
            t.paused=True
            t.attachments=[('image.png',[{'type':'image_url','image_url':{'url':'data:image/png;base64,AA=='}}])]
            pipe.send_text('\r');await asyncio.sleep(.2)
            self.assertEqual(len(t.queue),1)
            self.assertEqual(t.queue[0][0],'Describe the attached media.')
            self.assertEqual(t.queue[0][1][0][0],'image.png')
            self.assertEqual(t.attachments,[])

    async def test_slow_slash_keeps_editor_live_and_records_operator_result(self):
        started=threading.Event();release=threading.Event()
        async with self.terminal() as (app,t,pipe):
            def dispatch(command,*args,**kwargs):
                started.set();release.wait(2)
                return '{"window_open":false}'
            try:
                with patch.object(app,'dispatch',side_effect=dispatch):
                    pipe.send_text('/viewer status\r');await asyncio.sleep(.25)
                    self.assertTrue(started.is_set())
                    pipe.send_text('draft');await asyncio.sleep(.15)
                    self.assertEqual(t.input.text,'draft')
                    self.assertIsNotNone(t.pending)
                    pipe.send_text('\x03');await asyncio.sleep(.1)
                    self.assertEqual(t.input.text,'')
                    pipe.send_text('\x03');await asyncio.sleep(.1)
                    self.assertTrue(app.stop_event.is_set())
                    release.set();await asyncio.sleep(.3)
                    self.assertIsNone(t.pending)
                    self.assertEqual(t.action_panel[0],'/viewer status')
                    self.assertIn('cancel',t.action_panel[1].lower())
                    self.assertFalse(app.agent.history)
            finally:release.set()

    async def test_failed_attachment_keeps_new_draft_separate(self):
        started=threading.Event();release=threading.Event()
        async with self.terminal() as (app,t,pipe):
            def broken(path):
                started.set();release.wait(2);raise ValueError('bad image')
            try:
                with patch('terminal.interactive.attachment',side_effect=broken):
                    pipe.send_text('/attach missing.png\r');await asyncio.sleep(.2)
                    self.assertTrue(started.is_set())
                    pipe.send_text('next draft');await asyncio.sleep(.1)
                    release.set();await asyncio.sleep(.2)
                    self.assertEqual(t.input.text,'/attach missing.png\nnext draft')
                    self.assertEqual(t.attachments,[])
            finally:release.set()

    async def test_closed_viewer_choices_reopen_and_keep_closed(self):
        async with self.terminal() as (app,t,pipe):
            t.viewer_was_open=True
            with patch.object(app.viewer,'status',return_value={'window_open':False,'status':'closed'}),patch.object(app,'dispatch',return_value='Reopened') as dispatch:
                await asyncio.sleep(.2)
                self.assertEqual(t.viewer_choice,0)
                pipe.send_text('\x1b[B');await asyncio.sleep(.15)
                self.assertEqual(t.viewer_choice,1)
                pipe.send_text('\r');await asyncio.sleep(.2)
                dispatch.assert_not_called();self.assertIsNone(t.viewer_choice)
                t.viewer_was_open=True
                await asyncio.sleep(.2)
                pipe.send_text('\r');await asyncio.sleep(.3)
                dispatch.assert_called_once_with('/viewer')
                self.assertEqual(app.agent.history,[])

    async def test_task_arrows_only_cycle_running_and_drop_finished_tasks(self):
        async with self.terminal() as (app,t,pipe):
            ids={}
            for state in ('queued','waiting','blocked','succeeded','cancelled','running'):
                task=t.task_store.submit({'goal':state,'checks':[]})
                t.task_store.update(task['id'],state)
                ids[state]=task['id']
            second=t.task_store.submit({'goal':'second running','checks':[]})['id']
            t.task_store.update(second,'running')
            running={ids['running'],second}
            seen=set()
            for key in ('\x1b[C','\x1b[C','\x1b[D','\x1b[D'):
                pipe.send_text(key);await asyncio.sleep(.15)
                self.assertIn(t.selected_task,running)
                seen.add(t.selected_task)
            self.assertEqual(seen,running)
            ended=t.selected_task
            t.task_store.update(ended,'succeeded')
            t.task_poll_at=0
            await asyncio.sleep(.2)
            self.assertEqual(t.selected_task,(running-{ended}).pop())
            t.task_store.cancel(t.selected_task)
            t.task_poll_at=0
            await asyncio.sleep(.2)
            self.assertIsNone(t.selected_task)
            self.assertEqual(t.action_panel[1],'No running tasks.')
            pipe.send_text('\x1b[C');await asyncio.sleep(.15)
            self.assertIsNone(t.selected_task)
            self.assertEqual(len(t.task_store.list()),7)
