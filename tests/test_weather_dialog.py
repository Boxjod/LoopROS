"""Weather is an ordinary model-selected tool, not a sentence interceptor."""
import json
import tempfile
import unittest
from unittest.mock import patch
from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config
from model_fixture import call


class WeatherDialogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=App(load_config(),self.temp.name)

    def tearDown(self):
        self.app.close();self.temp.cleanup()

    def test_missing_city_question_and_fresh_queries_use_model_tool_loop(self):
        with patch('loop_robot.terminal.app.web_dispatch',side_effect=[{'location':'北京','temperature':29.8},{'location':'天津','temperature':30.2}]) as weather, patch.object(self.app.client,'complete',side_effect=[{'content':'哪个城市？'},call('web_weather',location='北京'),{'content':'北京29.8°C'},call('web_weather',location='天津'),{'content':'天津30.2°C'}]):
            self.assertEqual(self.app.agent.reply('天气怎么样'),'哪个城市？')
            weather.assert_not_called()
            self.assertEqual(self.app.agent.reply('北京'),'北京29.8°C')
            self.assertEqual(self.app.agent.reply('天津呢？'),'天津30.2°C')
            self.assertEqual([c.args[1]['location'] for c in weather.call_args_list],['北京','天津'])

    def test_weather_errors_and_permissions_are_tool_receipts(self):
        for denied in (False,True):
            self.app.permissions.set_rule('web_weather','deny' if denied else 'allow')
            with patch('loop_robot.terminal.app.web_dispatch',side_effect=RuntimeError('timeout')) as weather, patch.object(self.app.client,'complete',side_effect=[call('web_weather',location='北京'),{'content':'查询未完成。'}]) as model:
                self.assertEqual(self.app.agent.reply('北京天气'),'查询未完成。')
                receipts=[json.loads(m['content']) for m in model.call_args.args[0] if m['role']=='tool']
                self.assertEqual(receipts[-1]['error'],'PermissionError' if denied else 'RuntimeError')
                self.assertEqual(weather.call_count,0 if denied else 1)

    def test_weather_coding_and_followup_are_not_intercepted(self):
        self.app.agent.history=[{'role':'user','content':'北京天气'},{'role':'assistant','content':'哪个城市？'}]
        with patch('loop_robot.terminal.app.web_dispatch') as weather, patch.object(self.app.client,'complete',return_value={'content':'Coding response'}) as model:
            self.assertEqual(self.app.agent.reply('实现天气查询接口'),'Coding response')
            self.assertEqual(self.app.agent.reply('继续'),'Coding response')
            self.assertEqual(model.call_count,2)
            weather.assert_not_called()
