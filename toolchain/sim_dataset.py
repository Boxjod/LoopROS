"""ACT-shaped HDF5 transitions: observation[t], issued action[t], next observation[t]."""
import json
from pathlib import Path


class EpisodeWriter:
    def __init__(self, path, metadata):
        import h5py
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = h5py.File(self.path, 'x')
        self.count, self.shapes = 0, None
        self.file.attrs['sim'] = True
        self.file.attrs['complete'] = False
        self.file.attrs['metadata'] = json.dumps(metadata, allow_nan=False)
        self.file.attrs['action_alignment'] = 'observation[t] precedes action[t]; next_observations[t] follows it'

    def append(self, observation, action, next_observation, frames, evaluation, truncated=False):
        import numpy as np
        if next_observation['time'] <= observation['time']:
            raise ValueError('Transition must advance simulation time')
        arrays = {'observations/qpos':np.asarray(observation['qpos'],dtype=np.float64),
                  'observations/qvel':np.asarray(observation['qvel'],dtype=np.float64),
                  'next_observations/qpos':np.asarray(next_observation['qpos'],dtype=np.float64),
                  'action':np.asarray(action,dtype=np.float64),
                  'timestamps':np.asarray(observation['time']), 'next_timestamps':np.asarray(next_observation['time']),
                  'reward':np.asarray(evaluation['reward']), 'terminated':np.asarray(evaluation['success'] is True),
                  'truncated':np.asarray(truncated)}
        if any(not np.isfinite(arr).all() for arr in arrays.values()):
            raise ValueError('Nonfinite transition')
        for name, frame in frames.items():
            arrays['observations/images/'+name] = frame['rgb']
            arrays['observations/depth/'+name] = frame['depth']
            arrays['observations/segmentation/'+name] = frame['segmentation']
            arrays['observations/camera_to_world/'+name] = np.asarray(frame['calibration']['camera_to_world'])
            arrays['observations/intrinsics/'+name] = np.asarray(frame['calibration']['intrinsics'])
        shapes = {key:(arr.shape,str(arr.dtype)) for key,arr in arrays.items()}
        if self.shapes is not None and shapes != self.shapes:
            raise ValueError('Observation/action/camera schema changed during episode')
        self.shapes = shapes
        for key, arr in arrays.items():
            if key not in self.file:
                ds = self.file.create_dataset(key, shape=(0,)+arr.shape, maxshape=(None,)+arr.shape,
                                             chunks=True, dtype=arr.dtype)
            ds = self.file[key]
            ds.resize(self.count+1, axis=0); ds[self.count] = arr
        if self.count == 0:
            self.file.attrs['camera_metadata'] = json.dumps({n:{'calibration':f['calibration'],'labels':f.get('labels',{})} for n,f in frames.items()},allow_nan=False)
        self.count += 1

    def finish(self, evaluation):
        if not self.count: raise ValueError('Cannot complete an empty episode')
        self.file.attrs['evaluation'] = json.dumps(evaluation, allow_nan=False)
        self.file.attrs['complete'] = True
        self.file.flush(); self.file.close()
        return {'path':str(self.path.resolve()), 'transitions':self.count, 'evaluation':evaluation,
                'format':'ACT-shaped HDF5; action units/dimensions in metadata; training not performed'}

    def abort(self):
        self.file.close()  # Preserve incomplete evidence; loaders explicitly reject it.


def action_chunk(path, start, length, cameras):
    """Numpy sample for ACT/BC, padding mask excludes nonexistent future actions."""
    import h5py
    import numpy as np
    if type(start) is not int or type(length) is not int or length < 1:
        raise ValueError('Invalid start/chunk length')
    with h5py.File(path,'r') as f:
        if not f.attrs.get('complete',False): raise ValueError('Incomplete episode')
        total = f['action'].shape[0]
        if not 0 <= start < total: raise ValueError('start outside episode')
        count = min(length,total-start)
        actions = np.zeros((length,)+f['action'].shape[1:],dtype=np.float32)
        actions[:count] = f['action'][start:start+count]
        mask = np.arange(length)>=count
        images = {name:f['observations/images/'+name][start] for name in cameras}
        return {'images':images,'qpos':f['observations/qpos'][start], 'actions':actions,'is_pad':mask}


class TemporalActions:
    """Combine overlapping policy chunks. Real zero actions are valid predictions."""
    def __init__(self, dimension, max_chunks=32, decay=.1):
        import math
        if type(dimension) is not int or dimension<1 or type(max_chunks) is not int or not 1<=max_chunks<=256 or not math.isfinite(decay) or decay<0:
            raise ValueError('Invalid action aggregation parameters')
        self.dimension,self.max_chunks,self.decay=dimension,max_chunks,decay
        self.chunks=[]

    def add(self, start, actions):
        import numpy as np
        values=np.asarray(actions,dtype=np.float64)
        if type(start) is not int or start<0 or values.ndim!=2 or values.shape[1]!=self.dimension or not 1<=len(values)<=10000 or not np.isfinite(values).all():
            raise ValueError('Invalid action chunk')
        if any(s==start for s,_ in self.chunks): raise ValueError('Duplicate chunk start')
        self.chunks.append((start,values.copy()));self.chunks=sorted(self.chunks,key=lambda x:x[0])[-self.max_chunks:]

    def action(self, step):
        import numpy as np
        if type(step) is not int or step<0: raise ValueError('Invalid step')
        valid=[(s,a[step-s]) for s,a in self.chunks if s<=step<s+len(a)]
        if not valid: raise ValueError('No policy prediction covers this step')
        ages=np.asarray([step-s for s,_ in valid],dtype=float)
        weights=np.exp(-self.decay*(ages-ages.min()))
        return np.average([a for _,a in valid],axis=0,weights=weights)

    def reset(self): self.chunks.clear()
