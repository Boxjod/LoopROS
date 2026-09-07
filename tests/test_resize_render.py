"""Real terminal resizing while editing, completing and receiving output."""
import codecs
import fcntl
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from types import SimpleNamespace
from collections import deque

import pyte


class ResizeRenderTests(unittest.TestCase):
    def test_wide_panel_title_and_preview_stay_within_cell_width(self):
        from terminal.interactive import Terminal
        from terminal.markdown import BoldText
        from prompt_toolkit.utils import get_cwidth
        terminal = Terminal.__new__(Terminal)
        terminal.ui = SimpleNamespace(output=SimpleNamespace(get_size=lambda: SimpleNamespace(rows=8, columns=18)))
        terminal.input = SimpleNamespace(text='')
        terminal.queue = deque([('很长的中文排队消息🙂' * 10, [])])
        terminal.stream_text = '中文流式文本🙂' * 10
        terminal.stream_started = False
        terminal.stream_kind = 'answer_delta'
        terminal.markdown = BoldText()
        terminal.app = SimpleNamespace(node_focus='master')
        terminal.action_panel = ('中文标题🙂' * 10, '面板内容' * 10)
        terminal.panel_offset = 0
        for fragments in (terminal.prompt_text(), terminal.panel_fragments(3)):
            for line in ''.join(text for _, text in fragments).split('\n'):
                self.assertLessEqual(get_cwidth(line), 18, line)

    def test_repeated_resize_preserves_editor_and_panels(self):
        with tempfile.TemporaryDirectory() as directory:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
            screen = pyte.HistoryScreen(80, 24, history=5000)
            screen.write_process_input = lambda data: os.write(master, data.encode())
            parser = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen([sys.executable, str(Path(__file__).parent / 'fixtures/stream_terminal.py'), directory + '/state'],
                stdin=slave, stdout=slave, stderr=slave,
                env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=directory + '/home'))
            os.close(slave)
            raw = bytearray()

            def drain(seconds=.25):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    if select.select([master], [], [], .02)[0]:
                        try: data = os.read(master, 65536)
                        except OSError: return
                        raw.extend(data)
                        parser.feed(decoder.decode(data))

            def send(text, seconds=.25):
                os.write(master, text.encode())
                drain(seconds)

            def resize(rows, columns):
                screen.resize(rows, columns)
                fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))
                os.kill(process.pid, signal.SIGWINCH)
                drain()
                self.assertIsNone(process.poll())
                self.assertNotIn('Window too small', '\n'.join(screen.display))
                self.assertTrue(0 <= screen.cursor.y < rows)
                self.assertTrue(0 <= screen.cursor.x < columns)

            try:
                drain(.6)
                send('中文草稿🙂e\u0301' * 15 + '\n第二行\n最后XYZ')
                for rows, columns in ((8, 32), (5, 20), (3, 20), (2, 20), (1, 20), (24, 80), (6, 12), (40, 140), (12, 40)):
                    resize(rows, columns)
                    self.assertIn('最后XYZ', '\n'.join(screen.display))
                    self.assertIn('XYZ', screen.display[screen.cursor.y])
                send('\x1b[D!')
                self.assertIn('XY!Z', screen.display[screen.cursor.y])
                send('\x03')
                send('/cancel-turn\r')
                send('排队消息中文🙂' * 8 + '\r')
                send('队列旁草稿XYZ')
                for rows, columns in ((3, 20), (6, 24), (24, 80), (2, 20), (12, 40)):
                    resize(rows, columns)
                    self.assertIn('队列旁草稿XYZ', '\n'.join(screen.display))
                send('\x03')
                send('/queue clear\r')
                send('/queue resume\r')
                send('/permissions\r', .5)
                send('\x03')
                for rows, columns in ((6, 24), (24, 80), (5, 18), (12, 40)):
                    resize(rows, columns)
                    shown = '\n'.join(screen.display)
                    self.assertEqual(sum(line.startswith('❯ ') for line in screen.display), 1, shown)
                    self.assertIn('Actions', shown)
                send('\x1b', .5)
                send('/sw')
                for rows, columns in ((6, 18), (24, 100), (8, 30)):
                    resize(rows, columns)
                    shown = '\n'.join(screen.display)
                    self.assertIn('❯ /sw', shown)
                    self.assertEqual(shown.count('❯ /sw'), 1, shown)
                    self.assertIn('/switch', shown)
                send('\x03')
                send('你好\r', .1)
                send('流式草稿abc', .1)
                for rows, columns in ((6, 24), (24, 80), (8, 32), (12, 40)):
                    resize(rows, columns)
                    self.assertIn('流式草稿abc', '\n'.join(screen.display))
                drain(.6)
                send('\x03')
                send('/exit\r', .4)
                self.assertEqual(process.wait(timeout=5), 0)
                self.assertNotIn(b'\x1b[?1049h', raw)
                self.assertNotIn(b'Traceback', raw)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                os.close(master)
