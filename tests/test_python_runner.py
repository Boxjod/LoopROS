import hashlib
from pathlib import Path
import tempfile
import unittest
from terminal.app import App
from terminal.config import load_config

class PythonRunnerTests(unittest.TestCase):
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
