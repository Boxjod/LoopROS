import hashlib
from pathlib import Path
import tempfile
import unittest
from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config

class PythonRunnerTests(unittest.TestCase):
    def test_cancel_delivers_sigint_and_preserves_cleanup_receipt(self):
        import concurrent.futures
        import time
        with tempfile.TemporaryDirectory() as folder:
            app = App(load_config(), Path(folder)/'state'); app.workspace_root = Path(folder)
            app.permissions.set_rule('run_python', 'allow')
            path = Path(folder)/'interrupt.py'
            path.write_text('import signal,time\nfrom pathlib import Path\n'
                'def stop(*args):\n Path("cleaned").write_text("SIGINT")\n print("cleanup completed",flush=True)\n raise SystemExit(0)\n'
                'signal.signal(signal.SIGINT,stop)\nPath("ready").touch()\nwhile True: time.sleep(.02)\n')
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(app.tool, 'run_python', {'path': str(path),
                        'expected_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                    deadline = time.monotonic()+3
                    while not (Path(folder)/'ready').exists() and time.monotonic()<deadline: time.sleep(.01)
                    self.assertTrue((Path(folder)/'ready').exists())
                    app.stop_event.set()
                    result = future.result(timeout=3)
                self.assertEqual((Path(folder)/'cleaned').read_text(), 'SIGINT')
                self.assertEqual(result['stop_reason'], 'cancelled')
                self.assertEqual(result['returncode'], 0)
                self.assertIn('cleanup completed', result['stdout'])
                self.assertEqual(result['review']['verdict'], 'inconclusive')
            finally: app.close()

    def test_ignored_interrupt_does_not_force_kill_or_return_early(self):
        import concurrent.futures
        import time
        with tempfile.TemporaryDirectory() as folder:
            app = App(load_config(), Path(folder)/'state'); app.workspace_root = Path(folder)
            app.permissions.set_rule('run_python', 'allow')
            path = Path(folder)/'interrupt.py'
            path.write_text('import signal,time\nfrom pathlib import Path\n'
                'signal.signal(signal.SIGINT,signal.SIG_IGN)\nPath("ready").touch()\n'
                'while not Path("release").exists(): time.sleep(.02)\n')
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(app.tool, 'run_python', {'path': str(path),
                        'expected_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                    try:
                        deadline = time.monotonic()+3
                        while not (Path(folder)/'ready').exists() and time.monotonic()<deadline: time.sleep(.01)
                        self.assertTrue((Path(folder)/'ready').exists())
                        app.stop_event.set(); time.sleep(.15)
                        self.assertFalse(future.done())
                    finally: (Path(folder)/'release').touch()
                    self.assertEqual(future.result(timeout=3)['stop_reason'], 'cancelled')
            finally: app.close()

    def test_large_output_can_be_paged_without_reexecuting(self):
        import json
        from loop_robot.terminal.context_window import tool_text
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),Path(d)/'state');app.workspace_root=Path(d)
            try:
                app.permissions.set_rule('run_python','allow')
                path=Path(d)/'large.py'
                path.write_text('for i in range(2000): print(str(i) + ":" + "x" * 50)\nprint("FINAL_EVIDENCE")\n')
                result=app.tool('run_python',{'path':str(path),'expected_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
                preview=tool_text(result)
                self.assertLessEqual(len(preview),12000)
                receipt=json.loads(preview)
                self.assertEqual(receipt['returncode'],0)
                self.assertTrue(receipt['stdout_preview_truncated'])
                output=Path(receipt['stdout_path'])
                self.assertEqual(output.stat().st_mode & 0o777,0o600)
                tail=app.tool('read_file',{'path':str(output),'offset':2001,'limit':1})
                self.assertIn('FINAL_EVIDENCE',tail['content'])
                self.assertNotIn('FINAL_EVIDENCE',result['stdout'])
            finally:app.close()

    def test_permission_hash_stdout_stderr_and_failure(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),Path(d)/'state');app.workspace_root=Path(d)
            try:
                path=Path(d)/'check.py';path.write_text('import sys\nprint("✅ actual stdout")\nprint("error detail", file=sys.stderr)\nsys.exit(3)\n')
                args={'path':str(path),'expected_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                with self.assertRaises(PermissionError):app.tool('run_python',args)
                app.permissions.set_rule('run_python','allow')
                result=app.tool('run_python',args)
                self.assertEqual(result['returncode'],3)
                self.assertIn('✅ actual stdout',result['stdout']);self.assertIn('error detail',result['stderr'])
                self.assertTrue(Path(result['report']).exists())
                path.write_text('raise RuntimeError("changed")')
                with self.assertRaises(ValueError):app.tool('run_python',args)
                app.permissions.set_mode('plan')
                with self.assertRaises(PermissionError):app.tool('run_python',args)
            finally:app.close()

    def test_syntax_is_checked_before_process_launch(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            app=App(load_config(),Path(folder)/'state');app.workspace_root=Path(folder)
            try:
                app.permissions.set_rule('run_python','allow')
                path=Path(folder)/'bad.py';path.write_text('def broken(:')
                with patch('loop_robot.terminal.python_runner.subprocess.Popen', side_effect=AssertionError('Must not launch')):
                    with self.assertRaisesRegex(ValueError, 'syntax check failed'):
                        app.tool('run_python',{'path':str(path),'expected_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            finally:app.close()

    def test_timeout_output_limit_cancel_and_arguments_not_shell(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),Path(d)/'state');app.workspace_root=Path(d)
            app.permissions.set_rule('run_python','allow')
            try:
                path=Path(d)/'check.py'
                def execute(source,**extra):
                    path.write_text(source)
                    return app.tool('run_python',dict(path=str(path),expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),**extra))
                result=execute('import time\ntime.sleep(10)',timeout_s=1)
                self.assertEqual(result['stop_reason'],'timeout');self.assertNotEqual(result['returncode'],0)
                result=execute('while True: print("x" * 10000)')
                self.assertEqual(result['stop_reason'],'output_limit');self.assertTrue(result['truncated'])
                result=execute('import sys\nprint(sys.argv[1])',arguments=['$(touch should-not-exist)'])
                self.assertEqual(result['stdout'].strip(),'$(touch should-not-exist)')
                self.assertFalse((Path(d)/'should-not-exist').exists())
                app.stop_event.set()
                with self.assertRaises(RuntimeError):execute('print("not run")')
            finally:app.close()
