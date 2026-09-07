import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


class NetworkDiscoveryTests(unittest.TestCase):
    def load_module(self):
        spec = importlib.util.spec_from_file_location('network_discovery_under_test', Path(__file__).resolve().parents[1] / 'toolchain/network_discovery.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_import_has_no_command_execution(self):
        with patch('subprocess.run') as run:
            self.load_module()
            run.assert_not_called()

    def test_only_local_read_commands_and_selected_environment(self):
        module = self.load_module()
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '[]', '')) as run, \
                patch.dict('os.environ', {'ROS_DISTRO': 'test', 'UNRELATED_SECRET': 'not-for-output'}, clear=True):
            result = module.discover()
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ['ip', '-j', '-4', 'addr', 'show'], ['ip', '-j', '-4', 'route', 'show'], ['ip', '-j', 'neigh', 'show']])
        self.assertTrue(all(call.kwargs == {'capture_output': True, 'text': True, 'timeout': 8} for call in run.call_args_list))
        self.assertEqual(result['ros_distro'], 'test')
        self.assertIsNone(result['ros_master_uri'])
        self.assertNotIn('not-for-output', str(result))

    def test_failed_commands_do_not_abort_remaining_collection(self):
        module = self.load_module()
        with patch('subprocess.run', side_effect=[FileNotFoundError('ip missing'),
                   subprocess.TimeoutExpired(['ip'], 8), subprocess.CompletedProcess([], 1, '', 'failed')]):
            result = module.discover()
        self.assertIn('error', result['addresses'])
        self.assertIn('error', result['routes'])
        self.assertEqual(result['neighbors']['returncode'], 1)
