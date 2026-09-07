import tempfile
import unittest
from unittest.mock import patch
from terminal.app import App
from terminal.config import load_config
from terminal.scene_intent import direct_edit
from model_fixture import call

class SceneIntentTests(unittest.TestCase):
    def test_single_object_correction_and_typo(self):
        for text in ['生成一个衣柜','生产成一个衣柜','现在打开的是一个完整的场景啊我的妈,我需要的只要一个衣柜','我只需要一个衣柜，不要其他物品']:
            edit=direct_edit(text)
            self.assertEqual(edit['base'],'empty')
            self.assertEqual(edit['add'],[{'name':'wardrobe','kind':'wardrobe'}])
        self.assertEqual(direct_edit('生成一个电脑')['add'][0]['query'],'computer')

    def test_questions_negations_and_additions_not_replacement(self):
        for text in ['不要生成一个衣柜','怎么生成一个衣柜？','是否只需要一个衣柜','不要只生成一个衣柜','添加一个衣柜','在桌子上生成一个电脑']:
            self.assertIsNone(direct_edit(text),text)

    def test_model_selected_scene_executes_with_real_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            app=App(load_config(),directory)
            try:
                with patch.object(app.viewer,'open',return_value={'window_open':True,'reloaded':True}),patch.object(app.client,'complete',side_effect=[call('load_toolset',name='robotics'),call('generate_scene',description='我需要的只要一个衣柜'),{'content':'场景已保存。'}]):
                    app.tool('compose_scene',{'add':[{'name':'table','kind':'table'}]})
                    app.agent.history=[{'role':'assistant','content':'wardrobe is unsupported; scene_sha256 a1b2c3'}]
                    answer=app.agent.reply('我需要的只要一个衣柜')
                    self.assertEqual(set(app.scene_objects()),{'wardrobe'})
                    self.assertIn('场景',answer)
                    from toolchain.composition import state,load_spec
                    model,_=state(load_spec(app.latest_scene))
                    self.assertEqual(model.nu,2)
            finally: app.close()
