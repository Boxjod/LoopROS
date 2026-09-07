"""Owned desktop process with fresh heartbeats and acknowledged commands."""
import json
from pathlib import Path
import sys
import time
import queue
from model_assets import snapshot
from viewer_control import SimulationControl


def main():
    scene, ready = map(Path, sys.argv[1:3])
    inbox = ready.with_suffix('.command.json')
    loaded, error = {}, {}
    control = None
    last_command = None

    def publish(opened, **details):
        temporary = ready.with_suffix('.tmp')
        temporary.write_text(json.dumps({'window_open': opened, 'heartbeat': time.monotonic(),
                                        **loaded, **(control.snapshot() if control else {}),
                                        'last_command': last_command, **details}), encoding='utf-8')
        temporary.replace(ready)

    try:
        import mujoco
        import mujoco.viewer
        content, assets, digest = snapshot(scene)
        model = mujoco.MjModel.from_xml_string(content.decode('utf-8'), assets=assets)
        loaded = {'scene_sha256': digest,
                  'model_bodies': [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(1, model.nbody)],
                  'model_geoms': [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) for i in range(model.ngeom)],
                  'actuators': [{'name': mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i),
                                 'limited': bool(model.actuator_ctrllimited[i]),
                                 'range': model.actuator_ctrlrange[i].tolist()} for i in range(model.nu)]}
        data = mujoco.MjData(model)
        control = SimulationControl(mujoco, model, data)
        keys = queue.SimpleQueue()
        with mujoco.viewer.launch_passive(model, data, key_callback=keys.put) as viewer:
            with viewer.lock():
                control.apply({'action': 'camera', 'view': 'isometric'}, viewer)
            viewer.sync()
            publish(viewer.is_running())
            last_heartbeat = time.monotonic()
            while viewer.is_running():
                start = time.monotonic()
                while not keys.empty():
                    key = keys.get()
                    with viewer.lock():
                        control.keypress(key)
                command = None
                if inbox.exists():
                    command = json.loads(inbox.read_text())
                    inbox.unlink(missing_ok=True)
                if command:
                    try:
                        if time.monotonic() > command['expires']:
                            raise ValueError('Command expired without execution')
                        with viewer.lock():
                            result = control.apply(command['args'], viewer)
                            if command['args']['action'] in ('move_joints','move_cartesian'):
                                control.motion.result['id']=command['id']
                        last_command = {'id': command['id'], **result}
                    except (ValueError, KeyError, TypeError) as exc:
                        last_command = {'id': command.get('id'), 'executed': False, 'error': str(exc)}
                    viewer.sync()
                    publish(viewer.is_running())
                if not control.paused:
                    with viewer.lock():
                        control.motion.tick()
                        mujoco.mj_step(model, data)
                if time.monotonic() - last_heartbeat >= .05:
                    viewer.sync()
                    if control.paused:
                        with viewer.lock():
                            control.perturb_paused(viewer.perturb)
                    with viewer.lock():
                        selected = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, viewer.perturb.select) if viewer.perturb.select else None
                        loaded['mouse_selection'] = {'body': selected, 'active': int(viewer.perturb.active)}
                    if hasattr(viewer, 'set_texts'):
                        viewer.set_texts((None, mujoco.mjtGridPos.mjGRID_BOTTOMLEFT,
                            ('PAUSED' if control.paused else 'RUNNING') + ' | Selected: ' + (selected or 'none') + '\n'
                            'Space: pause / run | Backspace: reset\n'
                            'Double LEFT click: select | Ctrl + RIGHT drag: move\n'
                            'Paused: reposition free body | Running: apply force\n'
                            'Right panel > Control: actuator targets', ''))
                    publish(viewer.is_running())
                    last_heartbeat = time.monotonic()
                time.sleep(max(0, (.01 if control.paused else model.opt.timestep / control.speed) - (time.monotonic() - start)))
    except Exception as exc:
        error = {'error': str(exc)[:1000]}
        raise
    finally:
        publish(False, **error)


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from release_runtime import runtime_session
    with runtime_session():
        main()
