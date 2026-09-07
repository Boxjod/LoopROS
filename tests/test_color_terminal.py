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
class ColorTerminalTests(unittest.TestCase):
    def test_python_and_diff_colors_with_chinese_draft(self):
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
                send('配色', .4)
                os.write(master, '下一步检查'.encode())
                send(duration=2)
                shown='\n'.join(screen.display)
                self.assertIn('下一步检查',shown)
                self.assertIn('def greet():',shown)
                self.assertIn('+value = 42',shown)
                self.assertIn('-value = 1',shown)
                self.assertIn('中文注释',shown)
                colors={cell.fg for row in screen.buffer.values() for cell in row.values() if cell.data.strip()}
                self.assertGreaterEqual(len(colors),6)
                self.assertEqual((Path(folder)/'color_sample.py').read_text(),'value = 42\n')
                os.write(master,b'\x03')
                send(duration=.3)
                send('/exit')
                self.assertEqual(process.wait(timeout=5),0)
                self.assertNotIn(b'Master error',raw)
                self.assertNotIn(b'must not call the model',raw)
            finally:
                if process.poll() is None: process.kill();process.wait(timeout=5)
                os.close(master)
