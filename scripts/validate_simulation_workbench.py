"""Explicit bounded simulation/camera/dataset validation; never opens a GUI or trains."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher import _bootstrap
_bootstrap(legacy=False)


def run(backend,output,isaac_config=None):
    from loop_robot.toolchain.simulation import SimulationWorkbench
    output=Path(output)
    if output.exists(): raise ValueError('Choose a new validation output directory')
    service=SimulationWorkbench(output,isaac_config)
    created=service.call('sim_create',{'backend':backend,**({'scene':str(ROOT/'assets/simulation/simulation_workbench.xml')} if backend=='mujoco' else {})})
    instance=created['instance']
    def call(name,**kw): return service.call(name,{'instance':instance,**kw})
    try:
        if backend=='isaac':
            converted=call('sim_convert',source=str(ROOT/'examples/workbench_arm.urdf'),format='urdf',output=str((output/'arm.usd').resolve()))
            call('sim_edit',operation='robot',config={'name':'arm','path':converted['output'],'position':[0,0,.1]})
            call('sim_edit',operation='box',config={'name':'cube','position':[.4,0,.1],'size':[.2,.2,.2],'mass':.1})
        call('sim_camera',config={'name':'head','position':[0,0,2],'quaternion':[1,0,0,0],'width':160,'height':120})
        call('sim_camera',config={'name':'wrist_cam','parent':'wrist' if backend=='mujoco' else '/World/arm/wrist',
                                'position':[0,0,.3],'quaternion':[1,0,0,0],'width':160,'height':120})
        before=call('sim_capture',cameras=['head','wrist_cam'])
        # Task checks object presence; no claim of a trained reach/grasp policy.
        call('sim_task',task={'name':'camera_validation','seed':7,'horizon':5,'success':[{'kind':'exists','body':'cube'}]})
        call('sim_reset',seed=7)
        state=call('sim_inspect')
        action=[.2]*len(state['action'])
        episode=call('sim_record',actions=[action]*5,cameras=['head','wrist_cam'],steps=10)
        after=call('sim_capture',cameras=['head','wrist_cam'])
        import numpy as np, h5py
        np.testing.assert_allclose(before['cameras']['head']['camera_to_world'],after['cameras']['head']['camera_to_world'])
        if np.allclose(before['cameras']['wrist_cam']['camera_to_world'],after['cameras']['wrist_cam']['camera_to_world']):
            raise AssertionError('Wrist camera did not follow robot motion')
        with h5py.File(episode['path']) as f:
            if np.allclose(f['observations/qpos'][0],f['next_observations/qpos'][0]):
                raise AssertionError('Robot control did not change joint state')
            for name in ['head','wrist_cam']:
                if f['observations/images/'+name][0].var() <= 0: raise AssertionError('Uniform image')
        if backend=='isaac':
            if not any('cube' in str(v) for v in after['cameras']['head']['labels'].values()):
                raise AssertionError('Cube instance label missing')
            np.testing.assert_allclose(before['observation']['bodies']['arm'],[0,0,.1],atol=.002)
        result={'backend':backend,'version':state['version'],'before':before,'episode':episode,'after':after,
                'verification':'Real engine, cameras and aligned HDF5; object-presence task only, no training/grasp evaluation'}
        output.mkdir(parents=True,exist_ok=True)
        (output/'validation.json').write_text(json.dumps(result,indent=2,allow_nan=False))
        print(json.dumps({'report':str(output/'validation.json'),'backend':backend,'version':state['version'],'episode':episode},indent=2))
        return result
    finally:service.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--backend',choices=['mujoco','isaac'],required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--isaac-config',type=Path)
    args=parser.parse_args();run(args.backend,args.output,args.isaac_config)
