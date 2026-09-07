import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.install import windows_launcher
from terminal.platform_support import InputPoller, lock_terminal, venv_python


class PlatformTests(unittest.TestCase):
    def test_interpreter_layout(self):
        self.assertEqual(venv_python(Path("runtime"), windows=True), Path("runtime/Scripts/python.exe"))
        self.assertEqual(venv_python(Path("runtime"), windows=False), Path("runtime/bin/python"))

    def test_windows_pipe_reader(self):
        poller = InputPoller(io.StringIO("hello\nworld\n"), windows=True)
        self.assertEqual(poller.poll(1), "hello\n")
        self.assertEqual(poller.poll(1), "world\n")
        self.assertEqual(poller.poll(1), "")

    def test_windows_launcher_quotes_paths(self):
        content = windows_launcher(r"C:\用户\100%\loop.exe")
        self.assertIn('"C:\\用户\\100%%\\loop.exe" %*', content)
        self.assertIn("DisableDelayedExpansion", content)
        self.assertIn("chcp 65001", content)

    def test_windows_lock_adapter(self):
        api = Mock(LK_NBLCK=2)
        with tempfile.TemporaryFile("w+b") as stream:
            with patch("terminal.platform_support.os.name", "nt"), patch.dict(sys.modules, {"msvcrt": api}):
                lock_terminal(stream)
                api.locking.assert_called_once_with(stream.fileno(), 2, 1)
                api.locking.side_effect = OSError("busy")
                with self.assertRaises(BlockingIOError):
                    lock_terminal(stream)

    def test_real_lock_excludes_other_process(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "terminal.lock"
            with path.open("a+b") as stream:
                lock_terminal(stream)
                code = "from terminal.platform_support import lock_terminal; import sys; f=open(sys.argv[1],'a+b'); lock_terminal(f)"
                result = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"BlockingIOError", result.stderr)
            result = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
