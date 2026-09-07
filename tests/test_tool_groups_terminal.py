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
                self.assertIn('6 calls',shown)
                self.assertIn('保留中文草稿',shown)
                self.assertEqual(raw.count(b'Tool \xe2\x80\xba read_file'),0)
                self.assertNotIn(b'\x1b[?1000h', raw)
                os.write(master, b'\x0f')
                send(duration=.4)
                shown='\n'.join(screen.display)
                self.assertIn('Actions · /tools',shown)
                self.assertIn('保留中文草稿',shown)
                self.assertIn('not API billing',shown)
                title_row=next(i for i,line in enumerate(screen.display) if '[× Close]' in line)
                name_row=next(i for i,line in enumerate(screen.display) if 'read_file(' in line)
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
                os.write(master, b'\x1b[B')
                send(duration=.3)
                self.assertNotEqual(screen.display[title_row + 1], before)
                os.write(master, b'\x1b[A')
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
                from core.tasks import TaskStore
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
