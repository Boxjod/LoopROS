import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import install


class InstallTests(unittest.TestCase):
    def test_check_on_old_python_has_no_install_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(install, 'ROOT', Path(directory)), \
                 patch.object(install.Path, 'home', return_value=Path(directory)), \
                 patch.object(install.sys, 'argv', ['install.py', '--check']), \
                 patch.object(install.sys, 'version_info', (3, 8, 10)), \
                 patch.object(install.platform, 'python_version', return_value='3.8.10'), \
                 patch.object(install.platform, 'system', return_value='Linux'), \
                 patch.object(install.platform, 'release', return_value='test'), \
                 patch.object(install.platform, 'machine', return_value='x86_64'), \
                 patch.object(install, 'ensure_uv') as uv, \
                 patch.object(install.subprocess, 'run') as run, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                install.main()
            uv.assert_not_called()
            run.assert_not_called()
            self.assertIn('Python 3.12', output.getvalue())
            self.assertFalse((Path(directory) / '.venv').exists())

    def test_broken_environment_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / '.venv'
            env.mkdir()
            marker = env / 'keep'
            marker.write_text('user data')
            with self.assertRaisesRegex(SystemExit, 'preserved'):
                install.validate_environment(env)
            self.assertEqual(marker.read_text(), 'user data')

    @unittest.skipIf(os.name == 'nt', 'POSIX launcher behavior')
    def test_conflicting_launcher_prevents_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / '.local/bin'
            target.mkdir(parents=True)
            (target / 'loop').write_text('another program')
            with patch.object(install, 'ROOT', root), \
                 patch.object(install.Path, 'home', return_value=root), \
                 patch.object(install.sys, 'argv', ['install.py', '--terminal-only']), \
                 patch.object(install, 'ensure_uv') as uv:
                with self.assertRaisesRegex(SystemExit, 'left unchanged'):
                    install.main()
            uv.assert_not_called()
            self.assertEqual((target / 'loop').read_text(), 'another program')

    @unittest.skipIf(os.name == 'nt', 'POSIX launcher behavior')
    def test_replace_preview_failure_success_and_uninstall(self):
        import subprocess
        from scripts.uninstall import uninstall
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / '.local/bin'
            target.mkdir(parents=True)
            old_target = root / 'old/.venv/bin/loop'
            (target / 'loop').symlink_to(old_target)
            (target / 'loop.loop-ros-backup.1').write_text('prior backup')
            (target / 'loop-switch').write_text('old program')
            args = ['install.py', '--terminal-only', '--replace-launchers']
            with patch.object(install, 'ROOT', root), \
                 patch.object(install.Path, 'home', return_value=root), \
                 patch.object(install, 'ensure_uv', return_value='uv') as uv, \
                 contextlib.redirect_stdout(io.StringIO()):
                with patch.object(install.sys, 'argv', args + ['--check']):
                    install.main()
                uv.assert_not_called()
                self.assertEqual(os.readlink(target / 'loop'), str(old_target))
                self.assertFalse((target / 'loop.loop-ros-backup.2').is_symlink())
                with patch.object(install.sys, 'argv', args), \
                     patch.object(install.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'uv')):
                    with self.assertRaises(subprocess.CalledProcessError):
                        install.main()
                self.assertEqual(os.readlink(target / 'loop'), str(old_target))
                self.assertEqual((target / 'loop-switch').read_text(), 'old program')
                with patch.object(install.sys, 'argv', args), \
                     patch.object(install.subprocess, 'run') as run:
                    install.main()
                self.assertIn('--python', run.call_args.args[0])
                self.assertEqual(os.readlink(target / 'loop'), str(root / '.venv/bin/loop'))
                self.assertEqual(os.readlink(target / 'loop.loop-ros-backup.2'), str(old_target))
                self.assertEqual((target / 'loop.loop-ros-backup.1').read_text(), 'prior backup')
                self.assertEqual((target / 'loop-switch.loop-ros-backup.1').read_text(), 'old program')
                uninstall(root, root)
                self.assertFalse((target / 'loop').is_symlink())
                self.assertTrue((target / 'loop.loop-ros-backup.2').is_symlink())

    @unittest.skipIf(os.name == 'nt', 'POSIX launcher behavior')
    def test_replace_does_not_move_a_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.local/bin/loop').mkdir(parents=True)
            with patch.object(install, 'ROOT', root), \
                 patch.object(install.Path, 'home', return_value=root), \
                 patch.object(install.sys, 'argv', ['install.py', '--replace-launchers']), \
                 patch.object(install, 'ensure_uv') as uv:
                with self.assertRaisesRegex(SystemExit, 'directory'):
                    install.main()
            uv.assert_not_called()
            self.assertTrue((root / '.local/bin/loop').is_dir())
