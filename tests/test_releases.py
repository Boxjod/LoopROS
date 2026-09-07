import hashlib
import json
import unittest
from unittest.mock import patch
import release_client as release


class ReleaseTests(unittest.TestCase):
    def metadata(self, **changes):
        data = {"version": "0.2.0", "wheel": "loop_ros-0.2.0-py3-none-any.whl", "sha256": "a" * 64}
        data.update(changes)
        return json.dumps(data).encode()

    def test_version_comparison(self):
        with patch.object(release, "fetch", return_value=self.metadata()):
            self.assertTrue(release.check("https://example.invalid/loop", "0.1.9")["update_available"])
            self.assertFalse(release.check("https://example.invalid/loop", "0.2.0")["update_available"])
            self.assertFalse(release.check("https://example.invalid/loop", "0.10.0")["update_available"])

    def test_reject_unsafe_metadata(self):
        for changes in ({"wheel": "../../secret"}, {"sha256": "bad"}, {"version": "nightly"}):
            with self.subTest(changes=changes), patch.object(release, "fetch", return_value=self.metadata(**changes)):
                with self.assertRaises(ValueError):
                    release.manifest("https://example.invalid")

    def test_https_only(self):
        for url in ("http://example.invalid", "https://user:secret@example.invalid", "https://example.invalid?a=b"):
            with self.assertRaises(ValueError):
                release.base_url(url)

    def test_bad_hash_prevents_install(self):
        with patch.object(release, "fetch", side_effect=[self.metadata(), b"corrupt"]), patch.object(release.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                release.install("https://example.invalid")
            run.assert_not_called()
