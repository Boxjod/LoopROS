import tempfile
import unittest
from unittest.mock import patch
from loop_robot.terminal.mujoco_docs import lookup,context

class DocumentationTests(unittest.TestCase):
    def test_version_matching_official_pages_cache_and_bounded_excerpt(self):
        with tempfile.TemporaryDirectory() as directory, patch('loop_robot.terminal.mujoco_docs.local_version',return_value='3.12.0'), patch('loop_robot.terminal.mujoco_docs.request',return_value={'url':'https://mujoco.readthedocs.io/en/3.12.0/python.html','body':'<h1>MjSpec attach</h1><p>versioned evidence</p>','retrieved_at':'now'}) as get:
            result=lookup(directory)
            self.assertEqual(result['manual_version'],'3.12.0')
            self.assertIn('versioned evidence',result['text'])
            get.assert_called_once_with('https://mujoco.readthedocs.io/en/3.12.0/python.html')
            lookup(directory);self.assertEqual(get.call_count,1)
            self.assertIn('/en/3.12.0/',context()['matching_manual'])
            with self.assertRaises(ValueError): lookup(directory,version='../../private')

    def test_search_results_cannot_redirect_to_unofficial_domain(self):
        with tempfile.TemporaryDirectory() as directory, patch('loop_robot.terminal.mujoco_docs.local_version',return_value='3.12.0'), patch('loop_robot.terminal.mujoco_docs.dispatch',return_value={'results':[{'url':'https://evil.example/x'}]}), patch('loop_robot.terminal.mujoco_docs.request',return_value={'url':'https://mujoco.readthedocs.io/en/3.12.0/python.html','body':'attach','retrieved_at':'now'}) as get:
            lookup(directory,query='attach')
            get.assert_called_once_with('https://mujoco.readthedocs.io/en/3.12.0/python.html')
