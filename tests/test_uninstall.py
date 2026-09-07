import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from scripts.install import windows_launcher
from scripts.uninstall import owned_launcher, uninstall


class UninstallTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX symlinks and HOME')
    def test_real_cli_preview_remove_repeat_and_preserve_data(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root, home = base / 'source', base / 'home'
            (root / 'scripts').mkdir(parents=True)
            shutil.copy2(Path(__file__).resolve().parents[1] / 'scripts/uninstall.py', root / 'scripts/uninstall.py')
            venv = root / '.venv'
            venv.mkdir()
            (venv / 'pyvenv.cfg').write_text('home = /test\n')
            (root / 'artifacts').mkdir()
            (root / 'artifacts/session').write_text('history')
            (home / '.loop').mkdir(parents=True)
            (home / '.loop/config.json').write_text('{}')
            commands = home / '.local/bin'
            commands.mkdir(parents=True)
            (commands / 'loop').symlink_to(venv / 'bin/loop')  # Broken link is still owned.
            (commands / 'looper').symlink_to(base / 'another/.venv/bin/looper')
            (commands / 'loop-switch').write_text('another program')
            (commands / 'uv').write_text('shared uv')
            command = [sys.executable, str(root / 'scripts/uninstall.py')]
            env = dict(os.environ, HOME=str(home))
            subprocess.run(command + ['--check'], cwd=base, env=env, check=True, capture_output=True)
            self.assertTrue(venv.exists())
            self.assertTrue((commands / 'loop').is_symlink())
            for _ in range(2):
                subprocess.run(command, cwd=base, env=env, check=True, capture_output=True)
            self.assertFalse(venv.exists())
            self.assertFalse((commands / 'loop').is_symlink())
            self.assertTrue((commands / 'looper').is_symlink())
            self.assertEqual((commands / 'loop-switch').read_text(), 'another program')
            self.assertEqual((commands / 'uv').read_text(), 'shared uv')
            self.assertEqual((root / 'artifacts/session').read_text(), 'history')
            self.assertEqual((home / '.loop/config.json').read_text(), '{}')

    @unittest.skipIf(os.name == 'nt', 'POSIX symlinks')
    def test_linked_environment_target_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'external'
            target.mkdir()
            (target / 'keep').write_text('data')
            (root / '.venv').symlink_to(target, target_is_directory=True)
            with contextlib.redirect_stdout(io.StringIO()):
                uninstall(root, root)
            self.assertFalse((root / '.venv').is_symlink())
            self.assertEqual((target / 'keep').read_text(), 'data')

    def test_unrecognized_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.venv').mkdir()
            with self.assertRaisesRegex(SystemExit, 'unrecognized'):
                uninstall(root, root)
            self.assertTrue((root / '.venv').is_dir())

    def test_windows_launcher_matches_installer_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / '.venv'
            path = Path(directory) / 'loop.cmd'
            path.write_text(windows_launcher(env / 'Scripts/loop.exe'), encoding='utf-8')
            self.assertTrue(owned_launcher(path, env, 'loop', windows=True))
            path.write_text('another launcher')
            self.assertFalse(owned_launcher(path, env, 'loop', windows=True))

    @unittest.skipIf(os.name == 'nt', 'POSIX launcher behavior')
    def test_old_checkout_launchers_removed_then_normal_install_succeeds(self):
        from unittest.mock import patch
        from scripts import install
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'current'
            home = Path(directory) / 'home'
            old = Path(directory) / 'old/.venv/bin'
            old.mkdir(parents=True)
            commands = home / '.local/bin'
            commands.mkdir(parents=True)
            for name in ('loop', 'loop-switch', 'looper', 'looper-switch'):
                entry = 'switch_main' if name.endswith('-switch') else 'main'
                (old / name).write_text('#!/old/python\nfrom loop_robot.launcher import ' + entry + '\n')
                (commands / name).symlink_to(old / name)
            with contextlib.redirect_stdout(io.StringIO()):
                uninstall(root, home, check=True)
                self.assertTrue((commands / 'loop').is_symlink())
                uninstall(root, home)
                for name in ('loop', 'loop-switch', 'looper', 'looper-switch'):
                    self.assertFalse((commands / name).is_symlink())
                    self.assertTrue((old / name).is_file())
                # No replacement flag is required after uninstalling the old launchers.
                with patch.object(install, 'ROOT', root), \
                     patch.object(install.Path, 'home', return_value=home), \
                     patch.object(install.sys, 'argv', ['install.py', '--terminal-only']), \
                     patch.object(install, 'ensure_uv', return_value='uv'), \
                     patch.object(install.subprocess, 'run'):
                    install.main()
                self.assertEqual(os.readlink(commands / 'loop'), str(root / '.venv/bin/loop'))

    def test_other_checkout_windows_wrapper_is_recognized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'loop.cmd'
            path.write_text(windows_launcher(r'C:\old checkout\.venv\Scripts\loop.exe'), encoding='utf-8')
            self.assertTrue(owned_launcher(path, root / '.venv', 'loop', windows=True))
            path.write_text(windows_launcher(r'C:\other\tool.exe'), encoding='utf-8')
            self.assertFalse(owned_launcher(path, root / '.venv', 'loop', windows=True))

    def test_unrelated_python_and_comment_only_marker_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'loop'
            for content in ('from another_tool import main\n', '# from loop_robot.launcher import main\n'):
                path.write_text(content)
                self.assertFalse(owned_launcher(path, root / '.venv', 'loop'))
