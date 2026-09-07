import io
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from terminal.household_assets import convert, install, search
from toolchain.composition import primitive, state
from toolchain.viewer_control import SimulationControl

class HouseholdTests(unittest.TestCase):
    def test_search_excludes_description_only_wardrobe_hits(self):
        rows=[{'name':'Shoes','owner':'GoogleResearch','description':'wardrobe'},
              {'name':'Wardrobe','owner':'OpenRobotics'}]
        with patch('terminal.model_library.fetch',return_value=json.dumps(rows).encode()):
            self.assertEqual([m['model'] for m in search('衣柜')],['Wardrobe'])

    def test_archive_rejects_path_traversal(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as archive: archive.writestr('../escaped.obj','x')
        with tempfile.TemporaryDirectory() as directory, patch('terminal.model_library.fetch',side_effect=[b'{}',out.getvalue()]):
            with self.assertRaises(ValueError): install(directory,'https://fuel.gazebosim.org/1.0/GoogleResearch/models/test')

    def test_sdf_rejects_articulation_and_nonidentity_pose(self):
        for xml in ['<sdf><model><link/><joint/></model></sdf>',
                    '<sdf><model><pose>1 0 0 0 0 0</pose><link/></model></sdf>']:
            with self.assertRaises(ValueError): convert({'model.sdf':xml.encode()})

    def test_wardrobe_doors_move_and_ball_can_be_perturbed_while_paused(self):
        import mujoco
        model,data=state(primitive({'name':'wardrobe','kind':'wardrobe'}))
        data.ctrl[:]=.6
        mujoco.mj_step(model,data,nstep=500)
        self.assertTrue(all(data.qpos>.2))
        model,data=state(primitive({'name':'ball','kind':'sphere'}))
        control=SimulationControl(mujoco,model,data)
        control.keypress(32)
        self.assertTrue(control.paused)
        pert=mujoco.MjvPerturb(); pert.select=1
        scene=mujoco.MjvScene(model,maxgeom=100)
        mujoco.mjv_updateScene(model,data,mujoco.MjvOption(),None,mujoco.MjvCamera(),mujoco.mjtCatBit.mjCAT_ALL,scene)
        mujoco.mjv_initPerturb(model,data,scene,pert)
        pert.active=mujoco.mjtPertBit.mjPERT_TRANSLATE
        pert.refpos[:]=[.3,.2,.5]
        control.perturb_paused(pert)
        self.assertAlmostEqual(data.qpos[0],.3)
        self.assertAlmostEqual(data.qpos[2],.5)
        control.keypress(32);self.assertFalse(control.paused)
