"""Compile a verified asset snapshot in the managed MuJoCo environment."""
import json
import sys
import mujoco
from loop_robot.toolchain.model_assets import snapshot

content, assets, digest = snapshot(sys.argv[1])
model = mujoco.MjModel.from_xml_string(content.decode(), assets=assets)
data = mujoco.MjData(model)
if model.nkey:
    mujoco.mj_resetDataKeyframe(model, data, 0)
mujoco.mj_forward(model, data)
print(json.dumps({'compiled': True, 'scene_sha256': digest, 'bodies': model.nbody,
                  'joints': model.njnt, 'actuators': model.nu, 'task_success': 'not_evaluated'}))
