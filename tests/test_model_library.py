import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from loop_robot.terminal.model_library import install


class ModelLibraryTests(unittest.TestCase):
    def listing(self, data):
        return {'commit': 'a' * 40, 'models': ['test_arm'], 'entries': [
            {'path': 'test_arm/scene.xml', 'type': 'blob', 'mode': '100644', 'size': len(data),
             'sha': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}]}

    def test_verified_install_offline_cache_and_tamper_rejection(self):
        data = b'<mujoco><worldbody/></mujoco>'
        with tempfile.TemporaryDirectory() as directory:
            with patch('loop_robot.terminal.model_library.catalog', return_value=self.listing(data)), patch('loop_robot.terminal.model_library.fetch', return_value=data):
                result = install(directory, 'test_arm')
                self.assertFalse(result['cached'])
                self.assertTrue(Path(result['scene']).exists())
            with patch('loop_robot.terminal.model_library.catalog', side_effect=AssertionError('Cache must work offline')):
                self.assertTrue(install(directory, 'test_arm')['cached'])
                Path(result['scene']).write_text('<mujoco/>')
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    install(directory, 'test_arm')

    def test_bad_download_never_publishes_and_paths_rejected(self):
        data = b'<mujoco/>'
        with tempfile.TemporaryDirectory() as directory:
            with patch('loop_robot.terminal.model_library.catalog', return_value=self.listing(data)), patch('loop_robot.terminal.model_library.fetch', return_value=b'bad'):
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    install(directory, 'test_arm')
            self.assertFalse(list(Path(directory).glob('**/.loop-assets.json')))
            with self.assertRaises(ValueError):
                install(directory, '../test_arm')

    def test_public_mesh_pinned_download_and_local_reuse(self):
        from loop_robot.terminal.model_library import install_public,resolve
        import mujoco
        data=b'v 0 0 0\nv 0.1 0 0\nv 0 0.1 0\nv 0 0 0.1\nf 1 3 2\nf 1 2 4\nf 1 4 3\nf 2 3 4\n'
        entry={'path':'objects/tetra.obj','type':'blob','mode':'100644','size':len(data),'sha':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}
        def fetch(url,**kwargs):
            if '/commits/' in url: return json.dumps({'sha':'b'*40}).encode()
            if '/git/trees/' in url: return json.dumps({'tree':[entry]}).encode()
            return data
        with tempfile.TemporaryDirectory() as directory,patch('loop_robot.terminal.model_library.fetch',side_effect=fetch):
            result=install_public(directory,'https://github.com/example/objects/blob/main/objects/tetra.obj')
            from loop_robot.toolchain.model_assets import snapshot
            xml,assets,_=snapshot(result['scene'])
            self.assertEqual(mujoco.MjModel.from_xml_string(xml.decode(),assets=assets).nmesh,1)
            with patch('loop_robot.terminal.model_library.catalog',side_effect=AssertionError('local first')):
                self.assertTrue(resolve(directory,result['model'])['cached'])
            with self.assertRaises(ValueError): install_public(directory,'http://localhost/private.xml')
            with self.assertRaises(ValueError): install_public(directory,'https://github.com/a/b/blob/main/script.py')

    def test_missing_official_model_searches_public_web(self):
        from loop_robot.terminal.model_library import search
        with tempfile.TemporaryDirectory() as directory,patch('loop_robot.terminal.model_library.catalog',return_value={'models':[]}),patch('loop_robot.terminal.household_assets.search',return_value=[]),patch('loop_robot.terminal.web.dispatch',return_value={'results':[{'url':'https://github.com/example/objects/blob/main/cup.obj'}]}) as web:
            result=search(directory,'cup')
            self.assertIn('public_web',result['searched']);self.assertEqual(len(result['candidates']),1)
            web.assert_called_once()
