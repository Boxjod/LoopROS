"""Optional xterm.js reflow verification: XTERM_HEADLESS_MODULE points at a test install."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import test_resize_terminal as resize_tests


class ReflowScreen:
    def __init__(self):
        self.process = subprocess.Popen([shutil.which('node'), str(Path(__file__).parent/'fixtures/reflow_emulator.cjs')],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.display = []
        self.history = []
        self.write_process_input = lambda text: None

    def request(self, **kwargs):
        self.process.stdin.write(json.dumps(kwargs)+'\n'); self.process.stdin.flush()
        data = json.loads(self.process.stdout.readline())
        self.display, self.history = data['display'], data['history']
        for reply in data['replies']:
            self.write_process_input(reply)

    def resize(self, rows, columns):
        self.request(resize=[rows,columns])

    def feed(self, text):
        self.request(text=text)

    def close(self):
        self.process.terminate();self.process.wait(timeout=3)
        self.process.stdin.close();self.process.stdout.close()


@unittest.skipUnless(os.environ.get('XTERM_HEADLESS_MODULE') and shutil.which('node'), 'external xterm headless test dependency required')
class ResizeReflowTests(resize_tests.ResizeTerminalTests):
    def test_wrapped_chinese_draft(self):
        self.test_draft = '中文草稿' * 15 + '\n第二行'
        self.test_repeated_width_changes_keep_two_borders()

    def emulator(self, master):
        screen = ReflowScreen()
        self.addCleanup(screen.close)
        return screen, screen
