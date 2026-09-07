import io
import ssl
import socket
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from loop_robot.terminal.config import load_config
from loop_robot.terminal.llm import QwenClient, ModelAPIError, model_https_handler
from loop_robot.terminal.setup import ensure_setup


class ModelConnectionTests(unittest.TestCase):
    def test_missing_compiled_ca_paths_use_system_bundle(self):
        context = Mock()
        context.cert_store_stats.return_value = {'x509_ca': 0}
        with patch('loop_robot.terminal.llm.ssl.create_default_context', return_value=context), patch('loop_robot.terminal.llm.ssl.get_default_verify_paths', return_value=SimpleNamespace(cafile=None, capath=None)), patch('loop_robot.terminal.llm.os.environ', {}), patch('loop_robot.terminal.llm.Path.is_file', return_value=True), patch('loop_robot.terminal.llm.HTTPSHandler') as handler:
            model_https_handler()
            context.load_verify_locations.assert_called_once_with(cafile='/etc/ssl/certs/ca-certificates.crt')
            handler.assert_called_once_with(context=context)

    def test_explicit_or_existing_trust_store_not_replaced(self):
        for cafile, capath, count, env in [('/custom.pem', None, 0, {}), (None, '/custom/certs', 0, {}), (None, None, 1, {}), (None, None, 0, {'SSL_CERT_FILE': '/operator.pem'}), (None, None, 0, {'SSL_CERT_DIR': '/operator'})]:
            context = Mock()
            context.cert_store_stats.return_value = {'x509_ca': count}
            with patch('loop_robot.terminal.llm.ssl.create_default_context', return_value=context), patch('loop_robot.terminal.llm.ssl.get_default_verify_paths', return_value=SimpleNamespace(cafile=cafile, capath=capath)), patch('loop_robot.terminal.llm.os.environ', env), patch('loop_robot.terminal.llm.HTTPSHandler'):
                model_https_handler()
                context.load_verify_locations.assert_not_called()

    def test_safe_diagnostics_distinguish_transport_and_http(self):
        client = QwenClient(load_config()['llm'])
        client.key = 'test-key-never-print'
        cases = [(URLError(ssl.SSLCertVerificationError(1, 'private text')), 'TLS certificate'),
                 (URLError(socket.gaierror(-2, 'private hostname')), 'DNS'),
                 (URLError(TimeoutError('private URL')), 'timed out'),
                 (HTTPError('https://private.invalid', 401, 'private reason', {}, io.BytesIO(b'private body')), 'HTTP 401'),
                 (HTTPError('https://private.invalid', 404, 'private reason', {}, io.BytesIO(b'private body')), 'HTTP 404')]
        for error, expected in cases:
            with patch('loop_robot.terminal.llm.build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(ModelAPIError) as raised:
                    client.complete([{'role': 'user', 'content': 'OK'}], [])
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn('private', str(raised.exception))
                self.assertNotIn(client.key, str(raised.exception))
        with patch('loop_robot.terminal.setup.check_connection', side_effect=ModelAPIError('Model API HTTP 401: API key rejected')), patch('loop_robot.terminal.setup.recover_profile', return_value=None), patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertFalse(ensure_setup(Mock(), True))
            self.assertIn('HTTP 401', output.getvalue())
