import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terminal.app import App
from model_fixture import call
from terminal.config import load_config, ROOT
from toolchain.composition import compose, load_spec, state, geom_bounds
from toolchain.model_assets import snapshot


class CompositionTests(unittest.TestCase):
    def test_saved_scene_survives_state_directory_rename(self):
        with tempfile.TemporaryDirectory() as d:
            old=Path(d)/'old-checkout'
            app=App(load_config(),old)
            try:
                with patch.object(app.viewer,'open',return_value={'window_open':True,'reloaded':True}):
                    app.tool('compose_scene',{'add':[{'name':'table','kind':'table'}]})
                saved=json.loads((old/'scene_state.json').read_text())
                self.assertFalse(Path(saved['scene']).is_absolute())
                digest=snapshot(app.latest_scene)[2]
            finally: app.close()
            new=Path(d)/'Any Folder Name'
            old.rename(new)
            recovered=App(load_config(),new)
            try:
                self.assertEqual(recovered.latest_scene,new/saved['scene'])
                self.assertEqual(snapshot(recovered.latest_scene)[2],digest)
                # Existing absolute indexes remain readable if still valid.
                saved['scene']=str(recovered.latest_scene)
                (new/'scene_state.json').write_text(json.dumps(saved))
                recovered.latest_scene=None
                recovered.restore_scene_state()
                self.assertEqual(recovered.latest_scene,Path(saved['scene']))
            finally: recovered.close()

    def test_add_move_remove_preserve_scene_and_support(self):
        with tempfile.TemporaryDirectory() as d:
            first=compose({'base':'empty','add':[{'name':'table','kind':'table'},{'name':'chair','kind':'chair','position':[-1,0,0]}]},d)
            second=compose({'add':[{'name':'cube','kind':'box','support':'table'}]},d,current=first['scene'])
            self.assertEqual(set(second['objects']),{'table','chair','cube'})
            self.assertAlmostEqual(second['objects']['cube']['position'][2],.8)
            third=compose({'move':[{'name':'cube','support':'chair'}]},d,current=second['scene'])
            model,data=state(load_spec(third['scene']))
            self.assertAlmostEqual(data.body('cube/object').xpos[0],-1)
            self.assertAlmostEqual(data.body('cube/object').xpos[2],.5)
            fourth=compose({'remove':['cube']},d,current=third['scene'])
            self.assertEqual(set(fourth['objects']),{'table','chair'})
            self.assertEqual(Path(first['scene']).read_bytes(),snapshot(first['scene'])[0])
            with self.assertRaisesRegex(ValueError,'support'):
                compose({'remove':['table']},d,current=second['scene'])
            with self.assertRaisesRegex(ValueError,'bounds'):
                compose({'move':[{'name':'cube','support':'table','position':[9,0,0]}]},d,current=second['scene'])

    def test_panda_real_assets_pose_and_incremental_addition(self):
        from terminal.model_library import resolve
        directory=ROOT/'artifacts/terminal/models'
        if not list((directory/'franka_emika_panda').glob('*/.loop-assets.json')):
            self.skipTest('Official Panda asset cache unavailable')
        with tempfile.TemporaryDirectory() as d:
            result=compose({'add':[{'name':'table','kind':'table'},{'name':'chair','kind':'chair','position':[-1,0,0]},
                                   {'name':'panda','kind':'asset','query':'panda','support':'table'}]},d,resolve=lambda q,s:resolve(directory,q,s))
            self.assertEqual(result['joints'],9);self.assertEqual(result['actuators'],8)
            self.assertAlmostEqual(result['objects']['panda']['position'][2],.75,delta=.001)
            model,data=state(load_spec(result['scene']))
            self.assertAlmostEqual(data.joint('panda/joint4').qpos[0],-1.57079,delta=.001)
            self.assertAlmostEqual(data.ctrl[3],-1.57079,delta=.001)
            updated=compose({'add':[{'name':'ball','kind':'sphere','support':'table'}]},d,current=result['scene'])
            self.assertEqual(updated['joints'],10)
            loaded,_=state(load_spec(updated['scene']))
            self.assertEqual(loaded.njnt,10)
            self.assertEqual(updated['actuators'],8)
            self.assertEqual(set(updated['objects']),{'table','chair','panda','ball'})
            self.assertNotEqual(updated['objects']['ball']['position'][:2],[0,0])
            moved=compose({'move':[{'name':'panda','support':'chair'}]},d,current=updated['scene'])
            self.assertAlmostEqual(moved['objects']['panda']['position'][2],.45,delta=.001)

    def test_app_commits_only_real_scene_forces_reload_and_recovers_failure(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                with patch.object(app.viewer,'open',return_value={'window_open':True,'reloaded':True}) as opened:
                    first=app.tool('compose_scene',{'add':[{'name':'table','kind':'table'}]})
                    opened.assert_called_with(app.latest_scene,force=True)
                    with self.assertRaises(ValueError): app.tool('compose_scene',{'add':[{'name':'bad','kind':'script'}]})
                    self.assertEqual(str(app.latest_scene),first['scene'])
                    self.assertTrue(app.scene_generation_error)
                    app.tool('compose_scene',{'add':[{'name':'ball','kind':'sphere','support':'table'}]})
                    self.assertIsNone(app.scene_generation_error)
                    other=App(load_config(),d)
                    try: self.assertEqual(other.latest_scene,app.latest_scene)
                    finally: other.close()
                    for name,args in [('compose_scene',{'add':[]})]:
                        with self.assertRaises(ValueError): app.scheduled_tool(name,args)
                    app.permissions.set_mode('plan')
                    with self.assertRaises(PermissionError): app.tool('compose_scene',{'add':[]})
            finally: app.close()

    def test_model_prose_cannot_replace_actual_scene_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                response={'tool_calls':[{'id':'one','type':'function','function':{'name':'compose_scene','arguments':json.dumps({'add':[{'name':'chair','kind':'chair'}]})}}]}
                with patch.object(app.client,'complete',side_effect=[call('load_toolset',name='robotics'),response,{'content':'已写入/fake/scene.xml并完成抓取'}]) as llm, patch.object(app.viewer,'open',return_value={'window_open':True,'reloaded':True}):
                    answer=app.agent.reply('请处理木椅模型')
                self.assertTrue(app.latest_scene.exists())
                summary=app.agent.turn_summaries[-1]
                self.assertFalse(summary['answer_is_execution_evidence'])
                self.assertNotIn('/fake/',json.dumps(summary['tool_evidence']))
                self.assertIn(str(app.latest_scene),json.dumps(summary['tool_evidence']))
                self.assertEqual(llm.call_count,3)
            finally: app.close()

    def test_model_repairs_tool_geometry_without_another_user_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                def response(size):
                    return {'tool_calls':[{'id':str(len(size)),'type':'function','function':{'name':'compose_scene','arguments':json.dumps({'add':[{'name':'ball','kind':'sphere','size':size}]})}}]}
                with patch.object(app.client,'complete',side_effect=[call('load_toolset',name='robotics'),response([.1,.1,.1]),response([.1]),{'content':'ball geometry corrected'}]) as model, patch.object(app.viewer,'open',return_value={'window_open':True,'reloaded':True}):
                    answer=app.agent.reply('请处理球模型')
                self.assertEqual(model.call_count,4)
                self.assertIn('ball',app.scene_objects())
                self.assertIn(str(app.latest_scene),json.dumps(app.agent.turn_summaries[-1]['tool_evidence']))
                self.assertIsNone(app.scene_generation_error)
            finally: app.close()
