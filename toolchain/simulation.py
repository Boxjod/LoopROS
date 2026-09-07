"""Owned simulation instances and evidence. Same service for Loop and MCP."""
import json
from pathlib import Path
import threading
import uuid

from toolchain.sim_tasks import validate_task, evaluate


class SimulationWorkbench:
    def __init__(self, directory, isaac_config=None, cancelled=None):
        self.directory = Path(directory)
        self.isaac_config = isaac_config
        self.instances = {}
        self.lock = threading.RLock()
        self.cancelled = cancelled or (lambda: False)

    def create(self, backend, scene=None):
        if len(self.instances)>=4: raise ValueError('At most four owned simulation instances')
        if backend == 'mujoco':
            from toolchain.sim_mujoco import MujocoSimulation
            engine = MujocoSimulation(scene)
        elif backend == 'isaac':
            from toolchain.sim_isaac_client import IsaacSimulationClient
            engine = IsaacSimulationClient(self.isaac_config, scene)
        else: raise ValueError('backend must be mujoco or isaac')
        instance = uuid.uuid4().hex
        self.instances[instance] = {'engine':engine, 'task':None, 'steps':0, 'revision':0, 'episodes':0}
        return self.inspect(instance)

    def entry(self, instance):
        if instance not in self.instances: raise ValueError('Unknown or closed simulation instance')
        return self.instances[instance]

    def inspect(self, instance):
        entry = self.entry(instance)
        state = entry['engine'].inspect()
        return {**state,'instance':instance,'revision':entry['revision'], 'task':entry['task'],
                'evaluation':evaluate(state,entry['task'])}

    def call(self, name, args):
        with self.lock:
            result = self._call(name,args)
            self.directory.mkdir(parents=True,exist_ok=True)
            with (self.directory/'events.jsonl').open('a') as f:
                # Do not store frames or arbitrary connection configuration in the event log.
                f.write(json.dumps({'tool':name, 'instance':result.get('instance'), 'result':result}, allow_nan=False)+'\n')
            return result

    def _call(self, name, args):
        if name == 'sim_create': return self.create(**args)
        if name == 'sim_list': return {'instances':[self.inspect(i) for i in self.instances]}
        instance = args['instance']
        entry = self.entry(instance); engine = entry['engine']
        if name == 'sim_inspect': return self.inspect(instance)
        if name == 'sim_convert':
            if engine.backend!='isaac': raise ValueError('USD conversion requires an Isaac instance')
            return {'instance':instance,**engine.convert(args['source'],args['format'],args['output'])}
        if name in ('sim_edit','sim_camera'):
            result = engine.edit(args['operation'],args['config']) if name=='sim_edit' else engine.camera(args['config'])
            entry['revision'] += 1
            if engine.backend == 'isaac' and name == 'sim_edit': entry['steps']=0
            return {'instance':instance,'revision':entry['revision'],'result':result}
        if name == 'sim_reset':
            engine.reset(args.get('seed',0)); entry['steps']=0; entry['revision']+=1
            return self.inspect(instance)
        if name == 'sim_step':
            engine.step(args['action'],args.get('steps',1)); entry['steps']+=1
            result = self.inspect(instance)
            result['terminated'] = result['evaluation']['success'] is True
            result['truncated'] = bool(entry['task'] and entry['steps']>=entry['task']['horizon'] and not result['terminated'])
            return result
        if name == 'sim_task':
            entry['task']=validate_task(args['task']);entry['steps']=0
            return self.inspect(instance)
        if name == 'sim_capture':
            from toolchain.sim_cameras import save_capture
            before = self.inspect(instance)
            frames = engine.capture(args['cameras'])
            after = self.inspect(instance)
            if before['time'] != after['time']: raise RuntimeError('Capture advanced physics; reject unsynchronized frame')
            return {'instance':instance, **save_capture(self.directory/'captures'/uuid.uuid4().hex,after,frames)}
        if name == 'sim_record':
            return self.record(instance,args)
        if name == 'sim_close':
            engine.close();del self.instances[instance]
            return {'instance':instance,'closed':True}
        raise ValueError('Unknown simulation tool')

    def record(self, instance, args):
        from toolchain.sim_dataset import EpisodeWriter
        entry=self.entry(instance);engine=entry['engine']
        actions=args['actions']; cameras=args['cameras']; steps=args.get('steps',1)
        if not isinstance(actions,list) or not 1<=len(actions)<=1000:
            raise ValueError('Provide 1..1000 actions for a bounded demonstration')
        if type(steps) is not int or not 1<=steps<=1000: raise ValueError('steps must be 1..1000')
        # Validate every action before executing any of the episode.
        from toolchain.sim_cameras import vector
        state=self.inspect(instance)
        for action in actions:
            vector(action,len(state['action']), 'action')
            for value,bound in zip(action,state['action_space']['bounds']):
                if bound and not bound[0] <= value <= bound[1]: raise ValueError('Action outside limits')
        task=entry['task']
        if task is None: raise ValueError('Set a measurable task with sim_task before recording')
        if task['seed'] != state['seed']: raise ValueError('Use sim_reset with the task seed before recording')
        frames=engine.capture(cameras)
        # Reset is explicit; record starts from the current observed state.
        path=self.directory/'datasets'/task['name']/('variation'+str(task['variation']))/instance/('episode_'+str(entry['episodes'])+'.hdf5')
        writer=EpisodeWriter(path,{'instance':instance,'revision':entry['revision'],'task':task,
            'scene_sha256':state['scene_sha256'],'backend':state['backend'],'version':state['version'],
            'action_space':state['action_space'],'physics_steps_per_action':steps,'initial_observation':state})
        entry['episodes']+=1
        try:
            for i,action in enumerate(actions):
                if self.cancelled(): raise RuntimeError('Demonstration cancelled; partial episode retained as incomplete')
                before=self.inspect(instance)
                if i: frames=engine.capture(cameras)
                if self.inspect(instance)['time'] != before['time']: raise RuntimeError('Capture changed simulation time')
                engine.step(action,steps);entry['steps']+=1
                after=self.inspect(instance)
                evaluation=after['evaluation']
                truncated=entry['steps']>=task['horizon'] and evaluation['success'] is not True
                writer.append(before,action,after,frames,evaluation,truncated)
                if evaluation['success'] is True or truncated: break
            return {'instance':instance, 'dataset_dir':str(path.parent.resolve()), **writer.finish(evaluation)}
        except BaseException:
            writer.abort(); raise

    def close(self):
        with self.lock:
            errors=[]
            for instance,entry in self.instances.items():
                try: entry['engine'].close()
                except Exception as exc: errors.append({'instance':instance,'error':str(exc),'remote_stop':'unverified'})
            self.instances.clear()
            if errors:
                self.directory.mkdir(parents=True,exist_ok=True)
                (self.directory/'shutdown-errors.json').write_text(json.dumps(errors))
            return errors
