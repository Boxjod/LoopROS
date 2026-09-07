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
class OfflineSkillTerminalTests(unittest.TestCase):
    def test_skill_selection_chinese_input_without_model(self):
        with tempfile.TemporaryDirectory() as folder:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
            screen = pyte.HistoryScreen(100,30,history=5000)
            screen.write_process_input = lambda s: os.write(master,s.encode())
            stream = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen([sys.executable,str(Path(__file__).parent/'fixtures/offline_skill_terminal.py'),folder+'/state'],
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
                self.assertIn('离线控制台', send('/skills'))
                send('/skills run 离线控制台', 1)
                from terminal.offline_skills import node_name
                name = node_name('offline-console')
                send('/node send '+name+' 中文离线反馈', .5)
                os.write(master, '/skills logs 离线控制台'.encode())
                self.assertIn('离线控制台', send(duration=.5))
                os.write(master,b'\r')
                send(duration=.6)
                self.assertTrue('CHILD=中文离线反馈'.encode() in raw, '\n'.join(screen.display))
                send('/skills stop 离线控制台')
                send('/exit')
                self.assertEqual(process.wait(timeout=5),0)
                self.assertNotIn(b'Master error',raw)
                self.assertNotIn(b'must not call the model',raw)
            finally:
                if process.poll() is None: process.kill();process.wait(timeout=5)
                os.close(master)
