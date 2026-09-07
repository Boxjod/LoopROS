import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from terminal.app import App
from terminal.config import load_config
from terminal.command_display import format_command_result
from test_agent_ipc import request_worker


class AgentInteractionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'LOOP_HOME':self.temp.name+'/home','LOOP_TASK_AUTOSTART':'0'})
        self.env.start()
        self.app=App(load_config(),Path(self.temp.name)/'state')
        self.app.runtime.admission=None
        self.app.runtime.worker_target=request_worker
        self.app.client.key='fixture'
        self.agent=json.loads(self.app.dispatch('/spawn Planner wait'))

    def tearDown(self):
        self.app.close();self.env.stop();self.temp.cleanup()

    def test_slash_permissions_match_tools_and_preserve_message(self):
        for command, action in [('/agents','agents_status'),('/send @1 hello','send_agent'),
                                ('/result @1','agent_result'),('/agent-messages @1','agent_messages'),
                                ('/stop-agent @1','cancel_agent')]:
            self.app.permissions.set_rule(action,'deny')
            with self.assertRaises(PermissionError): self.app.dispatch(command)
            self.app.permissions.set_rule(action,'allow')
        value=json.loads(self.app.dispatch("/send @1 Don't change  the target"))
        self.assertEqual(value['message_id'],'@1:1')
        messages=json.loads(self.app.dispatch('/agent-messages @1'))['messages']
        self.assertEqual(messages[0]['message'],"Don't change  the target")
        self.app.permissions.set_mode('plan')
        with self.assertRaises(PermissionError): self.app.dispatch('/send @1 blocked')
        self.assertEqual(len(self.app.runtime.messages(self.agent['agent_id'])['messages']),1)

    def test_titles_stable_handles_and_readable_results(self):
        data=json.loads(self.app.dispatch('/agents active'))
        text=format_command_result('/agents',data)
        self.assertIn('wait · Planner @1',text)
        self.assertNotIn(self.agent['agent_id'],text)
        self.app.dispatch('/stop-agent @1')
        self.assertEqual(json.loads(self.app.dispatch('/agents active'))['tasks'],[])
        self.assertEqual(json.loads(self.app.dispatch('/result wait'))['state'],'cancelled')
        self.assertEqual(json.loads(self.app.dispatch('/agents all'))['tasks'][0]['reference'],'@1')
