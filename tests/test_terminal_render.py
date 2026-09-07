"""Optional rendered-screen regression: run with pyte available on PYTHONPATH."""
import codecs
import fcntl
import os
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
from pathlib import Path

try:
    import pyte
except ImportError:
    pyte = None


@unittest.skipUnless(pyte, 'pyte is required for rendered-screen validation')
class TerminalRenderTests(unittest.TestCase):
    def test_switch_options_visible_before_number_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 100, 0, 0))
            screen = pyte.HistoryScreen(100, 24, history=1000)
            screen.write_process_input = lambda data: os.write(master, data.encode())
            parser = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).parent / 'fixtures/stream_terminal.py'), directory + '/state'],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=Path(__file__).resolve().parents[1],
                env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=directory + '/home'))
            os.close(slave)
            raw = bytearray()
            def drain(seconds):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    if select.select([master], [], [], .02)[0]:
                        try: data = os.read(master, 65536)
                        except OSError: return
                        raw.extend(data)
                        parser.feed(decoder.decode(data))
            try:
                drain(.5)
                os.write(master, b'/switch\r')
                drain(.6)
                shown = '\n'.join(screen.display)
                self.assertIn('1. default-', shown)
                self.assertIn('2. default-', shown)
                self.assertIn('qwen-plus', shown)
                self.assertIn('Select a number', shown)
                self.assertLess(shown.index('1. default-'), shown.index('Select a number'))
                # Cancel without changing providers, then choose a real entry.
                os.write(master, b'\r')
                drain(.5)
                self.assertIn('Cancelled', bytes(raw).decode(errors='replace'))
                os.write(master, b'/switch\r')
                drain(.4)
                os.write(master, b'1\r')
                drain(.5)
                self.assertIn('Switched: ', bytes(raw).decode(errors='replace'))
                os.write(master, b'/exit\r')
                drain(.5)
                self.assertEqual(process.wait(timeout=3), 0)
                self.assertNotIn(b'\x1b[?1049h', raw)
            finally:
                if process.poll() is None: process.kill()
                process.wait(timeout=3)
                os.close(master)

    def test_operator_panel_scroll_and_close(self):
        for rows, columns in ((6, 24), (24, 100)):
            with self.subTest(rows=rows, columns=columns):
                self.check_operator_panel(rows, columns)

    def check_operator_panel(self, rows, columns):
        with tempfile.TemporaryDirectory() as directory:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))
            screen = pyte.HistoryScreen(columns, rows, history=1000)
            screen.write_process_input = lambda data: os.write(master, data.encode())
            parser = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).parent / 'fixtures/stream_terminal.py'), directory + '/state'],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=Path(__file__).resolve().parents[1],
                env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=directory + '/home'))
            os.close(slave)
            raw = bytearray()
            def drain(seconds):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    if select.select([master], [], [], .02)[0]:
                        try: data = os.read(master, 65536)
                        except OSError: return
                        raw.extend(data)
                        parser.feed(decoder.decode(data))
            try:
                drain(.5)
                os.write(master, b'/permissions\r')
                drain(.4)
                # Dismiss the selector so the panel can be inspected on a six-row screen.
                os.write(master, b'\x03')
                drain(.2)
                shown = '\n'.join(screen.display)
                self.assertIn('Actions · /permissions', shown)
                if rows > 6:
                    self.assertIn('Mode: sim', shown)
                self.assertNotIn('Window too small', shown)
                self.assertNotIn('● Permissions', shown)
                os.write(master, b'\x1b[6~')
                drain(.2)
                self.assertNotEqual(shown, '\n'.join(screen.display))
                os.write(master, b'\x1b')
                drain(1.8)
                self.assertNotIn('Actions · /permissions', '\n'.join(screen.display))
                prompt = next(i for i, line in enumerate(screen.display) if line.startswith('❯ '))
                self.assertEqual(screen.display[prompt + 1], '─' * (columns - 1) + ' ')
                os.write(master, '第一行\n第二行'.encode())
                drain(.2)
                prompt = next(i for i, line in enumerate(screen.display) if '❯ 第一行' in line)
                self.assertIn('第二行', screen.display[prompt + 1])
                os.write(master, b'\x03')
                drain(.2)
                prompt = next(i for i, line in enumerate(screen.display) if line.startswith('❯ '))
                self.assertEqual(screen.display[prompt - 1], '─' * (columns - 1) + ' ')
                new_rows, new_columns = rows + 3, columns + 5
                screen.resize(new_rows, new_columns)
                fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', new_rows, new_columns, 0, 0))
                os.kill(process.pid, signal.SIGWINCH)
                drain(.4)
                prompt = next(i for i, line in enumerate(screen.display) if line.startswith('❯ '))
                self.assertEqual(screen.display[prompt - 1], '─' * (new_columns - 1) + ' ')
                self.assertEqual(screen.display[prompt + 1], '─' * (new_columns - 1) + ' ')
                os.write(master, b'/exit\r')
                drain(.4)
                self.assertEqual(process.wait(timeout=3), 0)
            finally:
                if process.poll() is None: process.kill()
                process.wait(timeout=3)
                os.close(master)

    def test_queue_preview_and_up_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 100, 0, 0))
            screen = pyte.HistoryScreen(100, 24, history=1000)
            screen.write_process_input = lambda data: os.write(master, data.encode())
            parser = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).parent / 'fixtures/stream_terminal.py'), directory + '/state'],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=Path(__file__).resolve().parents[1],
                env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=directory + '/home'))
            os.close(slave)
            raw = bytearray()
            def drain(seconds):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    if select.select([master], [], [], .02)[0]:
                        try: data = os.read(master, 65536)
                        except OSError: return
                        raw.extend(data)
                        parser.feed(decoder.decode(data))
            try:
                drain(.5)
                os.write(master, b'/cancel-turn\r')
                drain(.3)
                os.write(master, '你好\r'.encode())
                drain(.3)
                shown = '\n'.join(screen.display)
                self.assertIn('Queued 1 · ❯ 你好', shown)
                self.assertIn('↑ edit queue', shown)
                os.write(master, b'\x1b[A')
                drain(.2)
                self.assertIn('❯ 你好', '\n'.join(screen.display))
                self.assertNotIn('Queued 1', '\n'.join(screen.display))
                os.write(master, '修改\r'.encode())
                drain(.3)
                self.assertIn('Queued 1 · ❯ 你好修改', '\n'.join(screen.display))
                os.write(master, b'/exit\r')
                drain(.4)
                self.assertEqual(process.wait(timeout=3), 0)
            finally:
                if process.poll() is None: process.kill()
                process.wait(timeout=3)
                os.close(master)

    def test_chinese_stream_queue_and_editing(self):
        for rows, columns in ((6, 24), (12, 40), (24, 80)):
            with self.subTest(rows=rows, columns=columns):
                self.check_screen(rows, columns)

    def check_screen(self, rows, columns):
        with tempfile.TemporaryDirectory() as directory:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ,
                        struct.pack('HHHH', rows, columns, 0, 0))
            screen = pyte.HistoryScreen(columns, rows, history=5000)
            screen.write_process_input = lambda data: os.write(master, data.encode())
            parser = pyte.Stream(screen)
            decoder = codecs.getincrementaldecoder('utf-8')()
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).parent / 'fixtures/stream_terminal.py'),
                 directory + '/state'], stdin=slave, stdout=slave, stderr=slave,
                cwd=Path(__file__).resolve().parents[1],
                env=dict(os.environ, TERM='xterm-256color', LOOPER_HOME=directory + '/home'))
            os.close(slave)
            raw = bytearray()

            def drain(seconds):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    if select.select([master], [], [], .02)[0]:
                        try:
                            data = os.read(master, 65536)
                        except OSError:
                            return
                        raw.extend(data)
                        parser.feed(decoder.decode(data))

            try:
                drain(.4)
                os.write(master, '你好\r'.encode())
                drain(.7)
                os.write(master, b'/per')
                drain(.2)
                self.assertIn('/permissions', '\n'.join(screen.display))
                os.write(master, b'\x03')
                drain(.15)
                self.assertNotIn(b'Unknown command', raw)
                os.write(master, b'11\r')
                drain(.15)
                os.write(master, '草稿ac\x1b[Db'.encode())
                drain(1)
                self.assertIn('❯ 草稿abc', '\n'.join(screen.display))
                prompt_row = next(i for i, line in enumerate(screen.display) if '❯ 草稿abc' in line)
                self.assertEqual(screen.display[prompt_row - 1], '─' * (columns - 1) + ' ')
                self.assertEqual(screen.display[prompt_row + 1], '─' * (columns - 1) + ' ')
                # Shrinking the editor must not insert padding above it.
                self.assertTrue(screen.display[prompt_row - 2].strip(), '\n'.join(screen.display))
                # Scrolling native history must not add rows to the transcript.
                before_rows = len(screen.history.top) + len(screen.history.bottom)
                before_display = screen.display[:]
                for _ in range(3):
                    screen.prev_page()
                    screen.next_page()
                self.assertEqual(screen.display, before_display)
                self.assertEqual(len(screen.history.top) + len(screen.history.bottom), before_rows)
                self.assertNotIn(b'RAW_JSON_SHOULD_BE_FOLDED', raw)
                self.assertIn(b'1 search', raw)
                os.write(master, b'\x03')
                drain(.15)
                os.write(master, b'/details\r')
                drain(.6)
                self.assertIn(b'RAW_JSON_SHOULD_BE_FOLDED', raw)
                os.write(master, b'\x03')
                drain(.4)
                self.assertEqual(process.wait(timeout=3), 0, bytes(raw)[-2000:])
                history = [''.join(row[x].data for x in range(columns))
                           for row in screen.history.top]
                flat = ''.join(line.rstrip() for line in history + screen.display)
                for text in ('推理起点', '推理终点', '我会调用相应', '工具或', '委派子任务。', '● 已收到11。'):
                    self.assertIn(text, flat)
                self.assertIn('Fast · available (probe only)', flat)
                self.assertIn('- 状态查询', flat)
                self.assertIn('- 仿真控制', flat)
                self.assertNotIn('Master ›', flat)
                self.assertNotIn('● - ', flat)
                self.assertNotIn('\ufffd', flat)
                self.assertNotIn(b'\x1b[?1049h', raw)
                cells=[cell for row in list(screen.history.top)+[screen.buffer[y] for y in range(rows)] for cell in row.values()]
                self.assertTrue(any(cell.data=='工' and cell.bold for cell in cells))
                self.assertTrue(any(cell.data=='委' and not cell.bold for cell in cells))
                self.assertNotIn('**', flat)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=3)
                os.close(master)

    def test_closed_viewer_panel_renders_and_dismisses(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'viewer-state.json'
            state.write_text(json.dumps({'window_open':True,'status':'open'}))
            master,slave=pty.openpty()
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
            screen=pyte.Screen(100,24);screen.write_process_input=lambda data:os.write(master,data.encode())
            parser=pyte.Stream(screen);decoder=codecs.getincrementaldecoder('utf-8')()
            process=subprocess.Popen([sys.executable,str(Path(__file__).parent/'fixtures/stream_terminal.py'),directory+'/state'],stdin=slave,stdout=slave,stderr=slave,cwd=Path(__file__).resolve().parents[1],env=dict(os.environ,TERM='xterm-256color',LOOP_HOME=directory+'/home'))
            os.close(slave)
            def drain(seconds):
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    if select.select([master],[],[],.02)[0]:
                        try:data=os.read(master,65536)
                        except OSError:return
                        parser.feed(decoder.decode(data))
            try:
                drain(.7)
                state.write_text(json.dumps({'window_open':False,'status':'closed'}))
                drain(.4)
                self.assertIn('Reopen last scene','\n'.join(screen.display))
                self.assertIn('Keep closed','\n'.join(screen.display))
                os.write(master,b'\x1b[B');drain(.2)
                self.assertIn('> Keep closed','\n'.join(screen.display))
                os.write(master,b'\r');drain(.2)
                self.assertNotIn('Reopen last scene','\n'.join(screen.display))
            finally:
                if process.poll() is None:process.kill()
                process.wait(timeout=3);os.close(master)
