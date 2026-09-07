import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from terminal.home import loop_home, looper_home, runtime_state_dir


class BrandingTests(unittest.TestCase):
    def test_runtime_state_migration_preserves_saved_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "looper"
            legacy.mkdir(mode=0o700)
            scene = legacy / "scene.xml"
            scene.write_text("saved-scene")
            scene.chmod(0o600)
            with patch.dict(os.environ, {"XDG_STATE_HOME": str(root)}, clear=True):
                current = runtime_state_dir(root / "installed-package")
                self.assertEqual(current, root / "loop-ros")
                self.assertEqual(scene.read_text(), "saved-scene")
                self.assertTrue(legacy.is_symlink())
                self.assertEqual((current / "scene.xml").read_text(), "saved-scene")
                if os.name != "nt":
                    self.assertEqual((current / "scene.xml").stat().st_mode & 0o777, 0o600)
                self.assertEqual(runtime_state_dir(root / "installed-package"), current)

    def test_state_migration_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "looper").mkdir()
            (root / "looper/history").write_text("preserve")
            with patch.dict(os.environ, {"XDG_STATE_HOME": str(root)}, clear=True), patch.object(Path, "symlink_to", side_effect=OSError):
                with self.assertRaisesRegex(ValueError, "original state preserved"):
                    runtime_state_dir(root / "package")
            self.assertEqual((root / "looper/history").read_text(), "preserve")
            self.assertFalse((root / "loop-ros").exists())

    def test_state_precedence_and_no_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("looper", "loop-ros"):
                (root / name).mkdir()
                (root / name / "history").write_text(name)
            with patch.dict(os.environ, {"XDG_STATE_HOME": str(root)}, clear=True):
                self.assertEqual(runtime_state_dir(root / "package"), root / "loop-ros")
                self.assertEqual((root / "looper/history").read_text(), "looper")
                (root / "pyproject.toml").touch()
                self.assertEqual(runtime_state_dir(root), root / "artifacts/terminal")
                with patch.dict(os.environ, {"LOOPER_STATE_DIR": str(root / "explicit-old")}):
                    self.assertEqual(runtime_state_dir(root), root / "explicit-old")
                    with patch.dict(os.environ, {"LOOP_STATE_DIR": str(root / "explicit-new")}):
                        self.assertEqual(runtime_state_dir(root), root / "explicit-new")
            self.assertIs(loop_home, looper_home)

    def test_installed_launch_aliases(self):
        for name, args in (("loop", []), ("loop", ["ros"]), ("loop", ["robot"]), ("looper", [])):
            program = Path(sys.executable).parent / (name + ".exe" if os.name == "nt" else name)
            if not program.exists():
                self.skipTest("Installed entry points required")
            result = subprocess.run([str(program), *args, "--version"], cwd=tempfile.gettempdir(),
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "Loop ROS 0.1.0")

    def test_home_compatibility(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {}, clear=True), patch("terminal.home.Path.home", return_value=root):
                self.assertEqual(looper_home(), root / ".loop")
                (root / ".looper").mkdir()
                (root / ".looper/config.json").write_text("{}")
                credential = root / ".looper/credentials.json"
                credential.write_text('{"fixture": "not-a-real-key"}')
                credential.chmod(0o600)
                self.assertEqual(looper_home(), root / ".loop")
                self.assertFalse((root / ".looper").exists())
                self.assertEqual((root / ".loop/config.json").read_text(), "{}")
                self.assertEqual((root / ".loop/credentials.json").read_text(), '{"fixture": "not-a-real-key"}')
                if os.name != "nt":
                    self.assertEqual((root / ".loop/credentials.json").stat().st_mode & 0o777, 0o600)
                (root / ".looper").mkdir()
                (root / ".looper/config.json").write_text("legacy")
                self.assertEqual(looper_home(), root / ".loop")
                self.assertEqual((root / ".loop/config.json").read_text(), "{}")
                self.assertEqual((root / ".looper/config.json").read_text(), "legacy")
                with patch.dict(os.environ, {"LOOP_HOME": str(root / "custom"), "LOOPER_HOME": str(root / "old")}):
                    self.assertEqual(looper_home(), root / "custom")
