import signal
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
class ResizeTerminalTests(unittest.TestCase):
    def emulator(self, master):
        screen = pyte.HistoryScreen(100,30,history=5000)
        return screen, pyte.Stream(screen)

    def test_repeated_width_changes_keep_two_borders(self):
        with tempfile.TemporaryDirectory() as folder:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
            screen, stream = self.emulator(master)
            screen.write_process_input = lambda s: os.write(master,s.encode())
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
                os.write(master,getattr(self, 'test_draft', '中文草稿').encode())
                send(duration=.2)
                for columns in [99,98,97,96,95,94,93,80,60,40,100,120,80,30,100]:
                    os.kill(process.pid, signal.SIGSTOP)
                    screen.resize(30, columns)
                    fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',30,columns,0,0))
                    os.kill(process.pid,signal.SIGWINCH)
                    os.kill(process.pid, signal.SIGCONT)
                    send(duration=.4)
                    lines = screen.display
                    borders = [line for line in lines if line.strip() and set(line.strip()) == {'─'}]
                    # CPR and the ensuing redraw are asynchronous. Inspect the
                    # settled frame, rather than the temporary erased region.
                    deadline = time.monotonic() + 2
                    while len(borders) < 2 and time.monotonic() < deadline:
                        send(duration=.1)
                        lines = screen.display
                        borders = [line for line in lines if line.strip() and set(line.strip()) == {'─'}]
                    self.assertEqual(len(borders),2,'width='+str(columns)+'\n'+'\n'.join(lines))
                    self.assertTrue(all(len(line.rstrip()) == columns-1 for line in borders))
                    self.assertIn('中文草稿','\n'.join(lines))
                    if isinstance(getattr(screen, 'history', None), list):
                        self.assertFalse(any(line.strip() and set(line.strip()) == {'─'} for line in screen.history))
                        transcript = ''.join(''.join(screen.history + lines).split())
                        self.assertIn('Ctrl-Dor/exittoleave.', transcript)
                os.write(master,b'\x03')
                send('/exit')
                self.assertEqual(process.wait(timeout=5),0)
            finally:
                if process.poll() is None: process.kill();process.wait(timeout=5)
                os.close(master)
