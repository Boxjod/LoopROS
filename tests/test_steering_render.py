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
class SteeringRenderTests(unittest.TestCase):
    def test_queued_chinese_input_joins_before_active_task_finishes(self):
        with tempfile.TemporaryDirectory() as folder:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 100, 0, 0))
            screen = pyte.Screen(100, 24)
            screen.write_process_input = lambda value: os.write(master, value.encode())
            stream = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen([sys.executable, str(Path(__file__).parent / 'fixtures/steering_terminal.py'), folder + '/state'],
                stdin=slave, stdout=slave, stderr=slave, env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=folder + '/home', LOOP_TASK_AUTOSTART='0'))
            os.close(slave)
            raw = bytearray()
            def drain(seconds):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    if select.select([master], [], [], .02)[0]:
                        try:
                            chunk = os.read(master, 65536)
                        except OSError:
                            break
                        raw.extend(chunk)
                        stream.feed(decoder.decode(chunk))
            try:
                drain(.6)
                os.write(master, '重新连接\r'.encode())
                deadline = time.monotonic() + 4
                while not Path(folder, 'state/probe-count').exists() and time.monotonic() < deadline:
                    drain(.1)
                self.assertTrue(Path(folder, 'state/probe-count').exists())
                os.write(master, '启动 loopmaster host\r'.encode())
                drain(.3)
                self.assertIn('Queued 1', '\n'.join(screen.display))
                os.write(master, '后续草稿'.encode())
                drain(2.4)
                self.assertIn('后续草稿', '\n'.join(screen.display))
                self.assertNotIn('Queued 1', '\n'.join(screen.display))
                self.assertIn('已合并新增要求'.encode(), raw)
                self.assertNotIn(b'Master error', raw)
                os.write(master, b'\x03')
                drain(.1)
                os.write(master, b'/exit\r')
                drain(.4)
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                os.close(master)
