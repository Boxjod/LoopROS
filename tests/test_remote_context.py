import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('remote_context_check', Path(__file__).resolve().parents[1]/'scripts/remote_context_check.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RemoteContextTests(unittest.TestCase):
    def test_match_change_missing_and_no_startup_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            record = root/'.loopros/context.json'
            record.parent.mkdir()
            script = root/'start.sh'
            script.write_text('exit 1\n')
            data = {'version':1, 'project_root':str(root),
                    'connection':{'observed_hostname':socket.gethostname()},
                    'files':{'start.sh':hashlib.sha256(script.read_bytes()).hexdigest()}}
            record.write_text(json.dumps(data))
            result = module.check(record)
            self.assertTrue(result['tracked_files_match'])
            self.assertEqual(result['current_readiness'], 'not_checked')
            self.assertIsNone(result['last_verified_startup'])
            script.write_text('exit 0\n')
            self.assertEqual(module.check(record)['changed'][0]['reason'], 'content_changed')
            script.unlink()
            self.assertEqual(module.check(record)['changed'][0]['reason'], 'missing')
            data['files'] = {'../secret':'ignored'}
            record.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'leaves project'):
                module.check(record)
