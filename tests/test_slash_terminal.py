import json
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
class SlashTerminalTests(unittest.TestCase):
    def test_menu_fast_and_chinese_during_stream(self):
        with tempfile.TemporaryDirectory() as folder:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
            screen = pyte.HistoryScreen(100,30,history=5000)
            screen.write_process_input = lambda s: os.write(master,s.encode())
            stream = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen([sys.executable,str(Path(__file__).parent/'fixtures/slash_terminal.py'),folder],
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
                self.assertIn('tasks 0', '\n'.join(screen.display))
                self.assertIn('Tokens 0', '\n'.join(screen.display))
                self.assertIn('Context ~', '\n'.join(screen.display))
                send('/context',.3)
                self.assertIn('stored messages', '\n'.join(screen.display))
                send('/compact',.3)
                self.assertIn('history preserved', '\n'.join(screen.display))
                send('/compact reset',.3)
                os.write(master,b'/')
                shown = send(duration=.3)
                shown = shown[shown.rfind('❯ /'):]
                indices = [shown.index(word) for word in ('/model','/mode ','/permissions','/resume','/help')]
                self.assertEqual(indices, sorted(indices))
                os.write(master,b'\x03')
                send('/model',.4)
                self.assertIn('model-a', '\n'.join(screen.display))
                send('model-b',.3)
                send('/fast',.3)
                self.assertIn('priority', '\n'.join(screen.display))
                send('/reasoning high',.4)
                self.assertIn('requested reasoning effort: high', '\n'.join(screen.display))
                send('中',.15)
                os.write(master,'文2'.encode())
                shown = send(duration=.4)
                self.assertIn('文2', shown)
                send('',.5)
                os.write(master,b'\r')
                send(duration=1)
                send('代码示例',1.5)
                shown = '\n'.join(screen.display)
                self.assertIn('Code · text',shown)
                row = next(i for i,line in enumerate(screen.display) if '/approve example-id' in line)
                column = screen.display[row].index('/approve')
                self.assertEqual(screen.buffer[row][column].bg,'262626')
                self.assertNotIn('```',shown)
                send('/exit')
                self.assertEqual(process.wait(timeout=5),0)
                inputs = [json.loads(line) for line in (Path(folder)/'inputs.jsonl').read_text().splitlines()]
                self.assertEqual(inputs,['中','文2','代码示例'])
                self.assertNotIn(b'Unknown command', raw)
                self.assertNotIn(b'Master error',raw)
            finally:
                if process.poll() is None: process.kill();process.wait(timeout=5)
                os.close(master)
