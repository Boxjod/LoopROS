import re
import unittest
from pathlib import Path

from terminal.app import HELP
from terminal.ui import welcome, VERSION, LOGO, TAGLINE


class WelcomeTests(unittest.TestCase):
    def test_wide_plain_banner(self):
        text = welcome("qwen-plus", "expert-test", "sim", cwd=Path("/tmp/demo"), color=False, width=100)
        for expected in (VERSION, "qwen-plus", TAGLINE, "/tmp/demo", "hardware disabled", "/help"):
            self.assertIn(expected, text)
        self.assertNotIn("expert-test", text)
        self.assertNotIn("Expert ·", text)
        custom = welcome("my-api-model", "hidden-expert", "sim", width=100)
        self.assertIn("Master · my-api-model", custom)
        self.assertNotIn("qwen-plus", custom)
        self.assertNotIn("\033", text)
        self.assertNotIn("flicker-free", text)

    def test_narrow_and_color(self):
        self.assertTrue(welcome("qwen", "expert", "plan", width=16).startswith("Loop ROS"))
        self.assertNotIn("\033", welcome("qwen", "expert", "sim", color=True))
        self.assertTrue(welcome("qwen", "expert", "sim", width=60).startswith("\n".join(LOGO)))

    def test_help_is_english(self):
        self.assertIsNone(re.search(r"[\u4e00-\u9fff]", str(HELP)))

    def test_solid_logo_and_alignment(self):
        self.assertEqual(LOGO[0][9], "█")
        self.assertEqual(LOGO[0].strip(), "█")
        self.assertEqual(LOGO[1], "     ▟▀▀▀▀▀▀▀▙")
        self.assertEqual(LOGO[2][8:11], "   ")
        self.assertLessEqual(set("".join(LOGO)), set(" █▀▄▟▙▜▛"))
        mirror = str.maketrans("▛▜▙▟", "▜▛▟▙")
        for row in LOGO[3:5]:
            self.assertEqual(row[12:17], row[2:7][::-1].translate(mirror))
            self.assertEqual(row[1:18], row[1:18][::-1].translate(mirror))
        self.assertEqual(LOGO[3][2:7], "▛   ▜")
        self.assertEqual(LOGO[4][2:7], "▙   ▟")
        # Three separated lower-half antenna strokes, raised by half a cell.
        self.assertEqual(LOGO[2][18:], "▄▄▄")
        self.assertEqual(LOGO[3][18:], "█▄▄")
        self.assertEqual(LOGO[4][18:], "█▄▄")
        self.assertEqual(LOGO[4][7:12], "██▀██")
        self.assertEqual(LOGO[3].count(" "), 6)
        self.assertEqual(LOGO[4].count(" "), 6)
        self.assertNotIn("▄▀▄", "".join(LOGO))
        self.assertEqual(sum(line.endswith("▄▄") for line in LOGO), 3)
        self.assertEqual(max(map(len, LOGO)), 21)
        self.assertEqual(len(LOGO), 6)
        banner = welcome("qwen", "expert", "sim", color=False, width=100)
        lines = banner.splitlines()
        self.assertEqual(lines[6], "")
        offset = max(map(len, LOGO)) + 2
        self.assertEqual(lines[0][offset:], "Loop ROS v" + VERSION)
        self.assertEqual(lines[1][offset:], TAGLINE)
        self.assertEqual(lines[2][offset:], "Master · qwen")
        self.assertTrue(all(line[offset:].strip() for line in lines[:6]))
