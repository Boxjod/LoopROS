"""PTY-screen validation of focus switching during Chinese model streaming."""
import codecs
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest

try:
    import pyte
except ImportError:
    pyte = None


@unittest.skipUnless(pyte and sys.platform.startswith('linux'), 'Linux PTY and pyte required')
class NodeTerminalTests(unittest.TestCase):
    def test_focus_and_control_while_master_streams(self):
        import fcntl
        import pty
        import struct
        import termios
        with tempfile.TemporaryDirectory() as directory:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 100, 0, 0))
            screen = pyte.HistoryScreen(100, 24, history=8000)
            screen.write_process_input = lambda data: os.write(master, data.encode())
            stream = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            root = Path(__file__).resolve().parents[1]
            process = subprocess.Popen([sys.executable, str(root/'tests/fixtures/node_terminal.py'), directory+'/state'],
                                       stdin=slave, stdout=slave, stderr=slave, cwd=root,
                                       env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=directory+'/home'))
            os.close(slave)
            raw = bytearray()
            def drain(seconds):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    if select.select([master], [], [], .02)[0]:
                        try:
                            data = os.read(master, 65536)
                        except OSError:
                            break
                        raw.extend(data)
                        stream.feed(decoder.decode(data))
            def send(text, pause=.3):
                os.write(master, (text+'\r').encode())
                drain(pause)
            try:
                drain(.5)
                send('/node start sim_arm arm', 1)
                send('开始分析', .2)
                send('/node use arm', .2)
                self.assertIn('[arm] ❯', '\n'.join(screen.display))
                self.assertIn('Terminal focus: arm', '\n'.join(screen.display))
                send('status', .2)
                send('move 0.3 -0.2', .3)
                send('master', .7)
                send('/node status arm', .4)
                panel_text='\n'.join(screen.display)
                for _ in range(8):
                    os.write(master,b'\x1b[6~');drain(.12)
                    panel_text+='\n'+'\n'.join(screen.display)
                self.assertIn('verdict: pass',panel_text)
                send('/node stop arm', .4)
                self.assertIn('process alive: no','\n'.join(screen.display))
                send('/exit', .5)
                self.assertEqual(process.wait(timeout=5), 0, raw[-3000:])
                history = [''.join(row[x].data for x in range(100)) for row in screen.history.top]
                flat = ''.join(line.rstrip() for line in history + screen.display)
                for phrase in ('Node arm', '后台分析完成'):
                    self.assertIn(phrase, flat)
                self.assertNotIn('Traceback', flat)
                self.assertNotIn('Wait for the active turn', flat)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                os.close(master)
