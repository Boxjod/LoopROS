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
try:
    import pyte
except ImportError:
    pyte = None


@unittest.skipUnless(pyte, 'pyte required')
class ToolGroupsTerminalTests(unittest.TestCase):
    def test_typed_stop_interrupts_live_python_instead_of_queueing(self):
        with tempfile.TemporaryDirectory() as folder:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 100, 0, 0))
            screen = pyte.HistoryScreen(100, 24, history=1000)
            screen.write_process_input = lambda value: os.write(master, value.encode())
            stream = pyte.Stream(screen); decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen([sys.executable, str(Path(__file__).parent/'fixtures/stream_terminal.py'), folder+'/state'],
                stdin=slave, stdout=slave, stderr=slave,
                env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=folder+'/home', LOOP_TASK_AUTOSTART='0'))
            os.close(slave)
            def drain(seconds):
                deadline = time.monotonic()+seconds
                while time.monotonic()<deadline:
                    if select.select([master], [], [], .02)[0]:
                        try: data = os.read(master, 65536)
                        except OSError: break
                        stream.feed(decoder.decode(data))
            try:
                drain(.6); os.write(master, '执行可中断脚本\r'.encode())
                deadline = time.monotonic()+4
                while not Path(folder, 'interrupt-ready').exists() and time.monotonic()<deadline: drain(.05)
                self.assertTrue(Path(folder, 'interrupt-ready').exists())
                os.write(master, '停止\r'.encode()); drain(.7)
                self.assertTrue(Path(folder, 'interrupt-cleaned').exists())
                shown = '\n'.join(screen.display)
                self.assertIn('SIGINT cleanup completed', shown)
                self.assertIn('Stop requested', shown)
                self.assertNotIn('停止 (queued)', shown)
                self.assertNotIn('Queued 1', shown)
                os.write(master, '中文草稿'.encode()); drain(.2)
                self.assertIn('中文草稿', '\n'.join(screen.display))
                os.write(master, b'\x03'); drain(.2); os.write(master, b'/exit\r'); drain(.4)
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)
                os.close(master)

    def test_stdout_and_progress_above_parallel_chinese_draft(self):
        with tempfile.TemporaryDirectory() as folder:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 100, 0, 0))
            screen = pyte.HistoryScreen(100, 24, history=1000)
            screen.write_process_input = lambda value: os.write(master, value.encode())
            stream = pyte.Stream(screen); decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen([sys.executable, str(Path(__file__).parent/'fixtures/stream_terminal.py'), folder+'/state'],
                stdin=slave, stdout=slave, stderr=slave,
                env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=folder+'/home', LOOP_TASK_AUTOSTART='0'))
            os.close(slave)
            def drain(seconds):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    if select.select([master], [], [], .02)[0]:
                        try: data = os.read(master, 65536)
                        except OSError: break
                        stream.feed(decoder.decode(data))
            try:
                drain(.6); os.write(master, '输出回执\r'.encode()); drain(.25)
                os.write(master, '中文草稿ac\x1b[Db'.encode()); drain(.6)
                shown = '\n'.join(screen.display)
                self.assertIn('状态已取得', shown)
                self.assertIn('Process exit: 0', shown)
                self.assertIn('已收到 3 帧', shown)
                self.assertIn('中文草稿abc', shown)
                prompt = next(i for i, line in enumerate(screen.display) if '❯ 中文草稿abc' in line)
                output = next(i for i, line in enumerate(screen.display) if '已收到 3 帧' in line)
                self.assertLess(output, prompt)
                self.assertNotIn('Tool ›', '\n'.join(screen.display[prompt+1:]))
                footer='\n'.join(screen.display[prompt+1:])
                for removed in ('Ready', 'queued', 'Session Tokens', 'Ctrl-V image'):
                    self.assertNotIn(removed,footer)
                self.assertIn('Context',footer)
                self.assertIn('/paste',footer)
                drain(1); os.write(master, b'\x03'); drain(.2)
                os.write(master, b'/exit\r'); drain(.4)
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)
                os.close(master)

    def test_details_scroll_without_capturing_main_transcript_mouse(self):
        with tempfile.TemporaryDirectory() as folder:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
            screen = pyte.HistoryScreen(100,30,history=5000)
            screen.write_process_input = lambda s: os.write(master,s.encode())
            stream = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen([sys.executable,str(Path(__file__).parent/'fixtures/stream_terminal.py'),folder+'/state'],
                stdin=slave,stdout=slave,stderr=slave,env=dict(os.environ,TERM='xterm-256color',LOOP_HOME=folder+'/home',LOOP_TASK_AUTOSTART='0'))
            os.close(slave)
            raw=bytearray()
            def send(text='', duration=.5):
                if text: os.write(master,(text+'\r').encode())
                deadline=time.monotonic()+duration
                while time.monotonic()<deadline:
                    if select.select([master],[],[],.02)[0]:
                        try: data=os.read(master,65536)
                        except OSError: break
                        raw.extend(data);stream.feed(decoder.decode(data))
                return '\n'.join(screen.display)
            try:
                send(duration=.6)
                send('折叠滚动', .4)
                os.write(master, '保留中文草稿'.encode())
                send(duration=1.2)
                shown='\n'.join(screen.display)
                self.assertIn('Tool › read_file',shown)
                input_row=next(i for i,line in enumerate(screen.display) if line.startswith('❯ ') and '保留中文草稿' in line)
                self.assertTrue(all(i < input_row for i,line in enumerate(screen.display) if 'Tool ›' in line))
                self.assertNotIn('Ctrl-O /tools','\n'.join(screen.display[input_row+1:]))
                self.assertIn('保留中文草稿',shown)
                self.assertGreaterEqual(raw.count(b'Tool \xe2\x80\xba read_file'),6)
                self.assertNotIn(b'\x1b[?1000h', raw)
                os.write(master, b'\x0f')
                send(duration=.4)
                shown='\n'.join(screen.display)
                self.assertIn('Actions · /tools',shown)
                self.assertIn('保留中文草稿',shown)
                self.assertIn('not API billing',shown)
                title_row=next(i for i,line in enumerate(screen.display) if '[× Close]' in line)
                name_row=next(i for i,line in enumerate(screen.display) if i > title_row and 'read_file(' in line)
                column=screen.display[name_row].index('read_file')
                self.assertEqual(screen.buffer[name_row][column].fg, '5fd7ff')
                self.assertIn('Working', shown)
                before = screen.display[title_row + 1]
                os.write(master, ('\x1b[<65;3;' + str(name_row+1) + 'M').encode())
                send(duration=.3)
                self.assertNotEqual(screen.display[title_row + 1], before)
                os.write(master, ('\x1b[<64;3;' + str(name_row+1) + 'M').encode())
                send(duration=.3)
                self.assertEqual(screen.display[title_row + 1], before)
                os.write(master, b'\x1b[6~')  # PageDown; arrows recall user input.
                send(duration=.3)
                self.assertNotEqual(screen.display[title_row + 1], before)
                os.write(master, b'\x1b[5~')
                send(duration=.3)
                self.assertEqual(screen.display[title_row + 1], before)
                self.assertIn('保留中文草稿', '\n'.join(screen.display))
                os.write(master, ('\x1b[<0;3;'+str(title_row+1)+'M\x1b[<0;3;'+str(title_row+1)+'m').encode())
                send(duration=.4)
                self.assertNotIn('Actions · /tools', '\n'.join(screen.display))
                self.assertIn('保留中文草稿', '\n'.join(screen.display))
                self.assertGreater(raw.rfind(b'\x1b[?1000l'), raw.rfind(b'\x1b[?1000h'))
                os.write(master, b'\x0f')
                send(duration=.4)
                self.assertIn('Actions · /tools', '\n'.join(screen.display))
                os.write(master,b'\x1b')
                send(duration=1.2)
                self.assertNotIn('Actions · /tools', '\n'.join(screen.display))
                Path(folder, 'release-scroll').touch()
                send(duration=.3)
                os.write(master,b'\x03')
                send(duration=.3)
                send('任务会话', .5)
                os.write(master, b'\x1b[C')
                send(duration=.3)
                shown = '\n'.join(screen.display)
                self.assertIn('Task Session', shown)
                self.assertIn('[Enter session]', shown)
                self.assertIn('[Close session]', shown)
                self.assertNotIn('View details', shown)
                self.assertGreater(raw.rfind(b'\x1b[?1000l'), raw.rfind(b'\x1b[?1000h'))
                os.write(master, b'\r')
                send(duration=.4)
                self.assertIn('Session · 检查机械臂', '\n'.join(screen.display))
                self.assertNotIn('Actions · Task Session', '\n'.join(screen.display))
                os.write(master, b'\x1b[C')
                send(duration=.2)
                os.write(master, b'\x1b[B\r')
                send(duration=.3)
                self.assertNotIn('Actions · Task Session', '\n'.join(screen.display))
                from loop_robot.core.tasks import TaskStore
                tasks = TaskStore(Path(folder) / 'state/tasks.sqlite').list()
                self.assertEqual(len(tasks), 1)
                self.assertEqual(tasks[0]['state'], 'queued')
                send('/exit')
                self.assertEqual(process.wait(timeout=5),0)
                self.assertNotIn(b'Master error',raw)
                self.assertNotIn(b'must not call the model',raw)
            finally:
                if process.poll() is None: process.kill();process.wait(timeout=5)
                os.close(master)
