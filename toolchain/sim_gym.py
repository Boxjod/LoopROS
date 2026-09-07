"""Optional Gymnasium adapter, using the same simulator and measurable task contract."""
import gymnasium as gym
import numpy as np

from toolchain.sim_tasks import validate_task, evaluate


class SimulationEnv(gym.Env):
    metadata = {'render_modes':['rgb_array']}

    def __init__(self, engine, task, cameras=(), frame_skip=10, render_mode=None):
        self.engine,self.task,self.cameras=engine,validate_task(task),list(cameras)
        self.frame_skip,self.render_mode=frame_skip,render_mode
        if type(frame_skip) is not int or not 1<=frame_skip<=1000: raise ValueError('Invalid frame_skip')
        state=engine.inspect()
        bounds=state['action_space']['bounds']
        if not bounds or any(b is None for b in bounds): raise ValueError('RL requires finite action bounds')
        self.action_space=gym.spaces.Box(np.array([b[0] for b in bounds],dtype=np.float32),np.array([b[1] for b in bounds],dtype=np.float32))
        spaces={'qpos':gym.spaces.Box(-np.inf,np.inf,shape=(len(state['qpos']),),dtype=np.float64)}
        for name in self.cameras:
            c=state['cameras'][name]
            spaces[name]=gym.spaces.Box(0,255,shape=(c['height'],c['width'],3),dtype=np.uint8)
        self.observation_space=gym.spaces.Dict(spaces)
        self.count=0;self.done=False

    def observation(self):
        state=self.engine.inspect()
        obs={'qpos':np.asarray(state['qpos'],dtype=np.float64)}
        if self.cameras: obs.update({n:f['rgb'] for n,f in self.engine.capture(self.cameras).items()})
        return obs,state

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.engine.reset(0 if seed is None else seed);self.count=0;self.done=False
        obs,state=self.observation()
        return obs,{'state':state,'evaluation':evaluate(state,self.task)}

    def step(self, action):
        if self.done: raise RuntimeError('Reset after terminated/truncated')
        self.engine.step(np.asarray(action).tolist(),self.frame_skip);self.count+=1
        obs,state=self.observation();evaluation=evaluate(state,self.task)
        terminated=evaluation['success'] is True
        truncated=self.count>=self.task['horizon'] and not terminated
        self.done=terminated or truncated
        return obs,evaluation['reward'],terminated,truncated,{'state':state,'evaluation':evaluation}

    def render(self):
        if not self.cameras: raise ValueError('Configure a render camera')
        return self.engine.capture(self.cameras[:1])[self.cameras[0]]['rgb']

    def close(self): self.engine.close()
