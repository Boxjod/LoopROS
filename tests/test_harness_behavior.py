import json
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from terminal.app import App
from terminal.config import load_config
from terminal.llm import ChatAgent
from terminal.tool_display import ToolDisplay
from model_fixture import call

class HarnessBehaviorTests(unittest.TestCase):
    def test_model_scene_dispatch_records_evidence_without_forced_reply(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d);events=[];app.agent.on_event=lambda k,v:events.append((k,v))
            result={'scene':'/test/verified.xml','viewer':{'window_open':True},'internal':'raw-metadata-sentinel'}
            try:
                with patch.object(app,'scene',return_value=result) as scene, patch.object(app.client,'complete',side_effect=[call('load_toolset',name='robotics'),call('generate_scene',description='生成一个桌子'),{'content':'The requested scene was saved.'}]):
                    answer=app.dispatch('生成一个桌子')
                scene.assert_called_once()
                self.assertEqual(answer,'The requested scene was saved.')
                self.assertTrue(any(k=='result' and 'raw-metadata-sentinel' in v for k,v in events))
                self.assertTrue(app.agent.turn_summaries[-1]['tool_evidence'])
            finally:app.close()

    def test_disabled_tool_stays_disabled_and_runtime_exposes_mode(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                app.permissions.set_mode('plan')
                self.assertEqual(app.agent.context_provider('hello')['live_context']()['permissions']['mode'],'plan')
                with patch.object(app.viewer,'open') as opened, patch.object(app.client,'complete',side_effect=[call('load_toolset',name='robotics'),call('generate_scene',description='桌子'),{'content':'Permission denied.'}]) as model:
                    self.assertEqual(app.dispatch('生成一个桌子'),'Permission denied.')
                    opened.assert_not_called()
                    receipts=[json.loads(m['content']) for m in model.call_args.args[0] if m['role']=='tool']
                    self.assertEqual(receipts[-1]['error'],'PermissionError')
            finally:app.close()

    def test_late_tool_result_after_cancel_is_recorded_without_success_reply(self):
        stop=threading.Event();events=[]
        client=SimpleNamespace(complete=lambda *a,**k:{'tool_calls':[{'id':'c1','function':{'name':'work','arguments':'{}'}}]})
        def dispatch(*args):stop.set();return {'executed':True,'action':'work'}
        agent=ChatAgent(client,[],dispatch,stop_event=stop)
        agent.result_summary=lambda results:'Done' if results else None
        agent.on_event=lambda k,v:events.append((k,v))
        with self.assertRaisesRegex(RuntimeError,'not rolled back'):agent.reply('work')
        self.assertTrue(any(k=='result' and json.loads(v)['executed'] for k,v in events))
        self.assertEqual(agent.turn_summaries[-1]['status'],'error')
        self.assertFalse(agent.history)

    def test_nested_failure_and_queued_are_not_displayed_as_success(self):
        display=ToolDisplay()
        for data,expected in [({'viewer':{'window_open':True,'review':{'verdict':'fail','reason':'hash mismatch'}}},'fail'),
                              ({'viewer':{'window_open':True,'error':'late failure'}},'late failure'),
                              ({'state':'queued','executed':True},'queued')]:
            summary=display.result(json.dumps(data),1)
            self.assertIn(expected,summary)
            self.assertNotIn('Scene loaded',summary)

    def test_numerical_tool_keeps_actual_receipt_without_forced_response(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                args={'current_A':2,'current_basis':'iq_peak','kt_Nm_per_A':.1,'kt_current_basis':'iq_peak','gear_ratio':10,'efficiency':.8}
                with patch.object(app.client,'complete',side_effect=[call('load_toolset',name='robotics'),call('motor_torque',**args),{'content':'Conditional output estimate: 1.6 N·m.'}]) as model:
                    self.assertEqual(app.agent.reply('计算力矩'),'Conditional output estimate: 1.6 N·m.')
                    receipts=[json.loads(m['content']) for m in model.call_args.args[0] if m['role']=='tool']
                    self.assertAlmostEqual(receipts[-1]['output_torque_Nm'],1.6)
            finally:app.close()

    def test_live_permissions_refresh_between_model_tool_rounds(self):
        mode={'value':'sim'};observed=[]
        def complete(messages,tools):
            context=next(m['content'] for m in messages if m.get('content','').startswith('Current runtime evidence'))
            observed.append(context)
            if len(observed)==1:return {'tool_calls':[{'id':'a','function':{'name':'check','arguments':'{}'}}]}
            return {'content':'Disabled'}
        def dispatch(*args):mode['value']='plan';return {'state':'queued'}
        agent=ChatAgent(SimpleNamespace(complete=complete),[],dispatch)
        agent.live_context=lambda:{'mode':mode['value']}
        self.assertEqual(agent.reply('check'),'Disabled')
        self.assertIn('sim',observed[0]);self.assertIn('plan',observed[1])

    def test_calculation_preamble_waits_for_receipt_without_affecting_plain_streams(self):
        events=[]
        def complete(messages,tools,on_event=None,stop_event=None):
            on_event('answer_delta','Unverified convention claim')
            return {'content':'Unverified convention claim','tool_calls':[{'id':'c','function':{'name':'calc','arguments':'{}'}}]}
        agent=ChatAgent(SimpleNamespace(complete=complete),[],lambda *args:{'value':1.6})
        agent.streaming=True;agent.defer_answer=lambda text:True
        agent.result_summary=lambda results:'Conditional estimate 1.6' if results else None
        agent.on_event=lambda k,v:events.append((k,v))
        self.assertEqual(agent.reply('calculate'),'Conditional estimate 1.6')
        self.assertFalse(any(k=='answer_delta' for k,v in events))
        self.assertTrue(any(k=='result' for k,v in events))

    def test_explicit_operator_grant_updates_existing_rules_without_motion(self):
        from terminal.permissions import ACTION_NAMES
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                app.permissions.set_mode('plan')
                app.permissions.set_rule('run_sim','deny')
                with patch.object(app.client,'complete',side_effect=AssertionError('No model needed')),patch.object(app,'tool') as tool:
                    answer=app.dispatch('允许所有执行权限')
                    tool.assert_not_called()
                state=app.permissions.snapshot()
                self.assertEqual(state['mode'],'sim')
                self.assertTrue(all(state['rules'][name]=='allow' for name in ACTION_NAMES))
                self.assertEqual(state['real_hardware'],'disabled')
                self.assertIn('对应型号',answer)
                self.assertNotIn('"hardware_writes"',answer)
            finally:app.close()

    def test_timer_cannot_grant_operator_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                app.permissions.set_mode('plan');app.permissions.set_rule('run_sim','deny')
                before=app.permissions.snapshot()
                with self.assertRaises(PermissionError):app.dispatch('允许所有执行权限',scheduled=True)
                self.assertEqual(app.permissions.snapshot(),before)
            finally:app.close()
