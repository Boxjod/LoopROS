import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terminal.app import App
from terminal.config import load_config
from terminal.skills import discover, prompt, read, write


class SkillsModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_write_read_discover_roundtrip(self):
        write(self.directory, "my-skill", "What this skill does.", "# My Skill\n\nDo the thing.")
        self.assertEqual(read(self.directory, "my-skill"),
                         "---\nname: my-skill\ndescription: \"What this skill does.\"\n---\n\n# My Skill\n\nDo the thing.")
        found = discover(self.directory)
        self.assertEqual(found, [{"name": "my-skill", "description": "What this skill does."}])
        self.assertIn("my-skill: What this skill does.", prompt(self.directory))

    def test_empty_directory_has_no_skills_and_empty_prompt(self):
        self.assertEqual(discover(self.directory), [])
        self.assertEqual(prompt(self.directory), "")

    def test_read_unknown_skill_raises(self):
        with self.assertRaises(ValueError):
            read(self.directory, "missing")

    def test_invalid_names_rejected(self):
        for bad in ("Bad-Name", "-leading", "trailing-", "double--hyphen", "a" * 65, "with space", "../escape"):
            with self.assertRaises(ValueError):
                write(self.directory, bad, "description", "content")

    def test_path_cannot_escape_skills_directory(self):
        with self.assertRaises(ValueError):
            write(self.directory, "..", "description", "content")

    def test_description_and_content_size_limits(self):
        with self.assertRaises(ValueError):
            write(self.directory, "ok", "x" * 1025, "content")
        with self.assertRaises(ValueError):
            write(self.directory, "ok", "description", "x" * 8001)
        with self.assertRaises(ValueError):
            write(self.directory, "ok", "two\nlines", "content")

    def test_directory_name_mismatch_is_not_discovered(self):
        (self.directory / "folder-name").mkdir()
        (self.directory / "folder-name" / "SKILL.md").write_text(
            "---\nname: different-name\ndescription: x\n---\n\nbody", encoding="utf-8")
        self.assertEqual(discover(self.directory), [])


class SkillToolPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"LOOP_HOME": self.home.name})
        self.env.start()
        self.app = App(load_config(), self.temp.name)

    def tearDown(self):
        self.app.close()
        self.env.stop()
        self.temp.cleanup()
        self.home.cleanup()

    def test_skill_write_defaults_to_ask_and_skill_read_does_not(self):
        self.assertEqual(self.app.permissions.snapshot()["rules"]["skill_write"], "ask")
        with self.assertRaises(PermissionError):
            self.app.tool("skill_write", {"name": "demo", "description": "d", "content": "c"})
        self.assertEqual(self.app.tool("skill_list", {}), {"skills": []})

    def test_allowed_skill_write_is_visible_to_skill_list_and_read(self):
        self.app.dispatch("/permissions allow skill_write")
        self.app.tool("skill_write", {"name": "demo", "description": "d", "content": "c"})
        self.assertEqual(self.app.tool("skill_list", {}), {"skills": [{"name": "demo", "description": "d"}]})
        self.assertIn("c", self.app.tool("skill_read", {"name": "demo"})["content"])
