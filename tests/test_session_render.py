import codecs
import fcntl
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
try: import pyte
except ImportError: pyte=None

@unittest.skipUnless(pyte,'pyte required')
class SessionRenderTests(unittest.TestCase):
    def test_task_buttons_and_permission_profiles(self):
        from core.tasks import TaskStore
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state'
            state.mkdir()
            store = TaskStore(state / 'tasks.sqlite')
            tasks = [store.submit({'goal': goal, 'checks': []}) for goal in ('检查电机状态', '核对机械臂反馈')]
            tasks.sort(key=lambda item: item['id'])
            for task in tasks:
                store.update(task['id'], 'running')
            queued = store.submit({'goal': '尚未启动', 'checks': []})
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
            screen = pyte.HistoryScreen(100, 30, history=1000)
            screen.write_process_input = lambda value: os.write(master, value.encode())
            parser = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen([sys.executable, str(Path(__file__).parent / 'fixtures/session_terminal.py'), str(state)],
                stdin=slave, stdout=slave, stderr=slave,
                env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=directory+'/home', LOOP_TASK_AUTOSTART='0'))
            os.close(slave)
            def send(text='', seconds=.4):
                if text: os.write(master, text.encode())
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    if select.select([master], [], [], .02)[0]:
                        try: data = os.read(master, 65536)
                        except OSError: break
                        parser.feed(decoder.decode(data))
                return '\n'.join(screen.display)
            try:
                send(seconds=.7)
                shown = send('\x1b[C')
                self.assertIn(tasks[0]['id'], shown)
                lines = screen.display
                input_row = next(i for i,line in enumerate(lines) if line.startswith('❯ '))
                task_row = next(i for i,line in enumerate(lines) if 'Actions · Tasks' in line)
                self.assertGreater(task_row, input_row)
                shown = send('\x1b[D')
                self.assertNotIn('Actions · Tasks', shown)
                self.assertTrue(all(store.get(t['id'])['state'] == 'running' for t in tasks))
                shown = send('\x1b[C')
                self.assertIn('Actions · Tasks', shown)
                shown = send('\x1b', 1.2)
                self.assertNotIn('Actions · Tasks', shown)
                shown = send('\x1b[C')
                shown = send('\x1b[C')
                self.assertIn(tasks[1]['id'], shown)
                shown = send('\x1b[C')
                self.assertNotIn('Actions · Tasks', shown)
                shown = send('\x1b[D')
                self.assertIn(tasks[1]['id'], shown)
                self.assertTrue(all(store.get(t['id'])['state'] == 'running' for t in tasks))
                self.assertNotIn(queued['id'], shown)
                shown = send('\x1b[B')
                self.assertIn('> [Cancel task]', shown)
                send('\r', .6)
                self.assertEqual(store.get(tasks[1]['id'])['state'], 'cancelled')
                self.assertEqual(store.get(tasks[0]['id'])['state'], 'running')
                self.assertEqual(store.get(queued['id'])['state'], 'queued')
                send('/permissions yo', .3)
                send('\x1b[B\r', .5)
                from terminal.permissions import PermissionGate
                gate = PermissionGate(state / 'permissions.sqlite')
                self.assertTrue(all(rule == 'allow' for rule in gate.snapshot()['rules'].values()))
                self.assertEqual(gate.snapshot()['rules']['policy_start'], 'allow')
                send('/permissions cautious\r', .5)
                self.assertTrue(all(rule == 'ask' for rule in gate.snapshot()['rules'].values()))
                send('/permissions default\r', .5)
                self.assertEqual(gate.snapshot()['rules']['policy_start'], 'ask')
                self.assertEqual(gate.snapshot()['rules']['devices'], 'allow')
                send('\x03', .3)
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                if process.poll() is None: process.terminate(); process.wait(timeout=5)
                os.close(master)

    def test_stream_summary_and_resume_selector(self):
        with tempfile.TemporaryDirectory() as directory:
            master,slave=pty.openpty()
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,80,0,0))
            screen=pyte.HistoryScreen(80,24,history=5000)
            screen.write_process_input=lambda value:os.write(master,value.encode())
            parser=pyte.Stream(screen);decoder=codecs.getincrementaldecoder('utf-8')();raw=bytearray()
            process=subprocess.Popen([sys.executable,str(Path(__file__).parent/'fixtures/session_terminal.py'),directory+'/state'],stdin=slave,stdout=slave,stderr=slave,env=dict(os.environ,TERM='xterm-256color',LOOP_HOME=directory+'/home'))
            os.close(slave)
            def drain(seconds):
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    if select.select([master],[],[],.02)[0]:
                        try: data=os.read(master,65536)
                        except OSError: return
                        raw.extend(data);parser.feed(decoder.decode(data))
            try:
                drain(.5);os.write(master,'解释电机\r'.encode());drain(.35)
                os.write(master,'草稿ac\x1b[Db'.encode());drain(1.3)
                self.assertIn('草稿abc','\n'.join(screen.display))
                self.assertNotIn(b'Summary',raw)
                self.assertNotIn('本轮总结'.encode(),raw)
                os.write(master,b'\x03');drain(.1)
                os.write(master,b'/switch ');drain(.4)
                self.assertIn('setup', '\n'.join(screen.display))
                lines = screen.display
                input_row = next(i for i,line in enumerate(lines) if '❯ /switch' in line)
                hint_row = next(i for i,line in enumerate(lines) if 'Configure provider' in line)
                self.assertGreater(hint_row, input_row)
                self.assertFalse(any('Configure provider' in line for line in lines[:input_row]))
                os.write(master,b'\x03');drain(.1)
                os.write(master,b'/resume\r');drain(.6)
                os.write(master,b'\x1b');drain(1.2)
                history=[''.join(row[x].data for x in range(80)) for row in screen.history.top]
                flat=''.join(line.rstrip() for line in history+screen.display)
                self.assertIn('本轮总结',flat)
                self.assertIn('Saved conversations',flat)
                self.assertIn('解释电机',flat)
                rows = list(screen.history.top) + [screen.buffer[y] for y in range(screen.lines)]
                user_rows = [row for row in rows if '❯ 解释电机' in ''.join(row[x].data for x in range(80))]
                self.assertTrue(user_rows)
                for row in user_rows:
                    marker = next(x for x in range(80) if row[x].data == '❯')
                    self.assertEqual(row[marker].bg, '303030')
                summary_rows = [row for row in rows if 'Summary' in ''.join(row[x].data for x in range(80))]
                self.assertFalse(summary_rows)
                self.assertNotIn(b'\x1b[?1049h',raw)
                os.write(master,b'\x03');drain(.15)
                os.write(master,'/rename 电机诊断\r'.encode());drain(.4)
                self.assertIn('Renamed: 电机诊断', '\n'.join(screen.display))
                os.write(master,'/sessions 电机诊断\r'.encode());drain(.4)
                self.assertIn('电机诊断', '\n'.join(screen.display))
                os.write(master,b'/export\r');drain(.4)
                self.assertIn('Exported:', '\n'.join(screen.display))
                exported = list((Path(directory) / 'state/exports').glob('*.md'))
                self.assertEqual(len(exported), 1)
                self.assertIn('解释电机', exported[0].read_text())
                os.write(master,b'\x1b');drain(.1);os.write(master,b'\x03');drain(.1);os.write(master,b'\x03');drain(.3)
                self.assertEqual(process.wait(timeout=5),0)
            finally:
                if process.poll() is None: process.terminate();process.wait(timeout=5)
                os.close(master)
