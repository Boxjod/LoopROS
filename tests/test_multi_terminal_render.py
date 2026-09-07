import codecs
import json
import os
from pathlib import Path
import select
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

try:
    import fcntl
    import pty
    import struct
    import termios
    import pyte
except ImportError:
    pyte = None


@unittest.skipUnless(pyte, 'Linux PTY and pyte required')
class MultiTerminalRenderTests(unittest.TestCase):
    def test_two_cli_windows_stream_drafts_and_resume_without_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)/'state'
            fixture = Path(__file__).parent/'fixtures/multi_terminal.py'
            windows = []
            def launch():
                master, slave = pty.openpty()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
                process = subprocess.Popen([sys.executable, str(fixture), str(state)],
                    stdin=slave, stdout=slave, stderr=slave,
                    env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=directory+'/home', LOOP_TASK_AUTOSTART='0'))
                os.close(slave)
                screen = pyte.HistoryScreen(80, 24, history=500)
                window = {'fd':master, 'process':process, 'screen':screen,
                          'parser':pyte.Stream(screen), 'decoder':codecs.getincrementaldecoder('utf-8')(), 'text':''}
                windows.append(window)
                return window
            def drain(seconds):
                end = time.monotonic()+seconds
                while time.monotonic()<end:
                    ready, _, _ = select.select([w['fd'] for w in windows], [], [], .02)
                    for w in windows:
                        if w['fd'] not in ready: continue
                        try: raw = os.read(w['fd'], 65536)
                        except OSError: continue
                        text = w['decoder'].decode(raw)
                        w['text'] += text
                        w['parser'].feed(text)
            def send(window, text):
                os.write(window['fd'], text.encode())
            def sessions():
                with sqlite3.connect(state/'conversation.sqlite') as db:
                    return [json.loads(row[0]) for row in db.execute('SELECT data FROM sessions')]
            try:
                a = launch(); drain(.7)
                send(a, '第一窗口独有问题\r'); drain(.15)
                send(a, '中文草稿甲'); drain(.8)
                b = launch(); drain(.7)
                send(b, '第二窗口独有问题\r'); drain(.15)
                send(b, '中文草稿乙'); drain(1)
                for w, draft in ((a, '中文草稿甲'), (b, '中文草稿乙')):
                    self.assertIsNone(w['process'].poll(), w['text'])
                    self.assertNotIn('Another terminal is using', w['text'])
                    self.assertIn(draft, '\n'.join(w['screen'].display))
                    self.assertIn('对话答复', w['text'])
                rows = sessions()
                first = next(row for row in rows if any(m.get('content')=='第一窗口独有问题' for m in row['history']))
                second = next(row for row in rows if any(m.get('content')=='第二窗口独有问题' for m in row['history']))
                self.assertNotEqual(first['session_id'], second['session_id'])
                self.assertNotIn('第二窗口独有问题', str(first['history']))
                self.assertNotIn('第一窗口独有问题', str(second['history']))
                send(b, '\x03'); drain(.2)
                send(b, '/resume 第一窗口独有问题'); drain(.3)
                send(b, '\r'); drain(1)
                self.assertIn('another terminal', b['text'])
                # Failed slash commands are intentionally restored for editing.
                send(b, '\x03'); drain(.2)
                send(a, '\x03'); drain(.2)
                send(a, '\x03'); drain(.7)
                self.assertEqual(a['process'].wait(timeout=5), 0, a['text'])
                self.assertIsNone(b['process'].poll())
                send(b, '/resume 第一窗口独有问题'); drain(.3)
                send(b, '\r'); drain(1)
                send(b, '继续输入中文'); drain(.4)
                self.assertIn('继续输入中文', '\n'.join(b['screen'].display))
                with sqlite3.connect(state/'conversation.sqlite') as db:
                    checkpoint = json.loads(db.execute('SELECT data FROM checkpoint WHERE id=1').fetchone()[0])
                self.assertEqual(checkpoint['session_id'], first['session_id'])
                send(b, '\x03'); drain(.2)
                send(b, '\x03'); drain(.7)
                self.assertEqual(b['process'].wait(timeout=5), 0, b['text'])
            finally:
                for w in windows:
                    if w['process'].poll() is None: w['process'].kill()
                    w['process'].wait(timeout=5)
                    os.close(w['fd'])
