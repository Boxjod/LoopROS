"""Validated commands applied only to the owned simulator, never hardware."""
import math


def validate(command):
    if not isinstance(command, dict):
        raise ValueError('Expected command object')
    action = command.get('action')
    fields = {'pause': set(), 'resume': set(), 'reset': set(), 'step': {'steps'},
              'speed': {'value'}, 'camera': {'view'}, 'actuate': {'values'}, 'move_joints': {'robot','target','duration'}, 'move_cartesian': {'robot','body','position','duration'}, 'stop_motion':set()}
    if action not in fields or set(command) - {'action'} != fields[action]:
        raise ValueError('Invalid simulator command arguments')
    if action == 'step' and (type(command['steps']) is not int or not 1 <= command['steps'] <= 1000):
        raise ValueError('steps must be 1..1000')
    if action == 'speed' and (type(command['value']) not in (int, float) or not math.isfinite(command['value']) or not .1 <= command['value'] <= 4):
        raise ValueError('speed must be 0.1..4')
    if action == 'camera' and command['view'] not in ('front', 'back', 'left', 'right', 'top', 'isometric'):
        raise ValueError('Unknown camera view')
    if action in ('move_joints','move_cartesian'):
        vector=command['target'] if action=='move_joints' else command['position']
        if not isinstance(command['robot'],str) or not command['robot'] or not isinstance(vector,list) or not 1<=len(vector)<=32 or any(type(v) not in (int,float) or not math.isfinite(v) for v in vector):raise ValueError('Invalid motion target')
        if action=='move_cartesian' and (len(vector)!=3 or not isinstance(command['body'],str)):raise ValueError('Expected body and xyz')
        if type(command['duration']) not in (int,float) or not math.isfinite(command['duration']) or not .2<=command['duration']<=30:raise ValueError('duration must be .2..30 seconds')
    if action == 'actuate':
        values = command['values']
        if not isinstance(values, list) or not 1 <= len(values) <= 256 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError('Expected finite actuator control values')
    return command


class SimulationControl:
    def __init__(self, mujoco, model, data):
        self.mj, self.model, self.data = mujoco, model, data
        self.paused, self.speed = False, 1.0
        self.reset()
        try:
            from toolchain.viewer_motion import Motion
        except ModuleNotFoundError:
            from viewer_motion import Motion
        self.motion=Motion(mujoco,model,data)

    def reset(self):
        if self.model.nkey:
            self.mj.mj_resetDataKeyframe(self.model, self.data, 0)
        else:
            self.mj.mj_resetData(self.model, self.data)
        try:
            from toolchain.viewer_motion import repair_invalid_home
        except ModuleNotFoundError:
            from viewer_motion import repair_invalid_home
        repair_invalid_home(self.mj,self.model,self.data)

    def apply(self, command, viewer):
        validate(command)
        action = command['action']
        if action in ('move_joints','move_cartesian'):
            self.motion.start(command)
            self.paused=False
        elif action == 'stop_motion':
            self.motion.stop()
        elif action == 'pause':
            self.motion.stop()
            self.paused = True
        elif action == 'resume':
            self.paused = False
        elif action == 'reset':
            self.motion.stop('Simulation reset')
            self.reset()
            self.paused = True
        elif action == 'step':
            if not self.paused:
                raise ValueError('Pause before single stepping')
            self.mj.mj_step(self.model, self.data, nstep=command['steps'])
        elif action == 'speed':
            self.speed = float(command['value'])
        elif action == 'camera':
            azimuth, elevation = {'front': (90, 0), 'back': (-90, 0), 'left': (180, 0),
                                  'right': (0, 0), 'top': (90, -89.9), 'isometric': (135, -25)}[command['view']]
            viewer.cam.lookat[:] = self.model.stat.center
            viewer.cam.distance = max(1, self.model.stat.extent * 1.5)
            viewer.cam.azimuth, viewer.cam.elevation = azimuth, elevation
        elif action == 'actuate':
            values = command['values']
            if len(values) != self.model.nu:
                raise ValueError('Expected exactly %d actuator values; inspect simulator_status' % self.model.nu)
            for i, value in enumerate(values):
                if not self.model.actuator_ctrllimited[i]:
                    raise ValueError('Actuator lacks declared control limits')
                lo, hi = self.model.actuator_ctrlrange[i]
                if not lo <= value <= hi:
                    raise ValueError('Actuator %d outside [%g, %g]' % (i, lo, hi))
            self.motion.stop('Replaced by direct actuator command')
            self.data.ctrl[:] = values
        return {'action': action, 'executed': True, **self.snapshot()}

    def keypress(self, key):
        if key == 32:
            self.motion.stop('Keyboard pause')
            self.paused = not self.paused
        elif key == 259:  # GLFW Backspace
            self.motion.stop('Keyboard reset')
            self.reset()
            self.paused = True

    def perturb_paused(self, perturb):
        if self.paused and perturb.select > 0 and perturb.active:
            self.mj.mjv_applyPerturbPose(self.model, self.data, perturb, 1)
            self.mj.mj_forward(self.model, self.data)

    def snapshot(self):
        return {'motion':self.motion.result if hasattr(self,'motion') else {'state':'idle'}, 'paused': self.paused, 'speed': self.speed, 'simulation_time': float(self.data.time),
                'qpos': self.data.qpos.tolist(), 'qvel': self.data.qvel.tolist(),
                'ctrl': self.data.ctrl.tolist(), 'contacts': int(self.data.ncon),
                'joints': [{'name': self.mj.mj_id2name(self.model,self.mj.mjtObj.mjOBJ_JOINT,i),
                            'type': int(self.model.jnt_type[i]), 'qpos_address': int(self.model.jnt_qposadr[i]),
                            'limited': bool(self.model.jnt_limited[i]), 'range': self.model.jnt_range[i].tolist(),
                            'axis': self.model.jnt_axis[i].tolist()} for i in range(self.model.njnt)],
                'body_poses': {self.mj.mj_id2name(self.model,self.mj.mjtObj.mjOBJ_BODY,i) or str(i):
                               {'position':self.data.xpos[i].tolist(),'quaternion':self.data.xquat[i].tolist()}
                               for i in range(1,self.model.nbody)}}
