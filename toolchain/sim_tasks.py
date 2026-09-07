"""Measurable task conditions shared by rollout, scene review and demonstrations."""
import math
from toolchain.sim_cameras import identifier, vector


def validate_task(task):
    if not isinstance(task,dict) or set(task)-{'name','description','variation','seed','success','horizon'}:
        raise ValueError('Invalid task fields')
    value = {'description':'', 'variation':0, 'seed':0, 'horizon':200, **task}
    identifier(value.get('name'))
    for key in ('variation','seed','horizon'):
        if type(value[key]) is not int or value[key] < (1 if key == 'horizon' else 0):
            raise ValueError('Invalid task '+key)
    if not isinstance(value['description'],str) or value['horizon'] > 10000:
        raise ValueError('Invalid task description or horizon')
    criteria = value.get('success')
    if not isinstance(criteria,list) or not 1 <= len(criteria) <= 32:
        raise ValueError('Task needs 1..32 measurable success conditions')
    for c in criteria:
        if not isinstance(c,dict): raise ValueError('Condition must be an object')
        kind = c.get('kind')
        fields = {'position': {'body','target','tolerance'}, 'exists':{'body'},
                  'above':{'body','support','tolerance'}, 'max_speed':{'value'}, 'max_penetration':{'value'}}
        if kind not in fields or set(c) != {'kind'} | fields[kind]:
            raise ValueError('Invalid success condition fields')
        for key in ('body','support'):
            if key in c and (not isinstance(c[key],str) or not c[key]): raise ValueError('Body name required')
        if kind == 'position': vector(c['target'],3,'target')
        for key in ('tolerance','value'):
            if key in c and (isinstance(c[key],bool) or not isinstance(c[key],(float,int)) or not math.isfinite(c[key]) or c[key]<0):
                raise ValueError('Condition threshold must be finite and nonnegative')
    return value


def evaluate(observation, task):
    if task is None:
        return {'success':None, 'verdict':'inconclusive', 'reward':0., 'checks':[]}
    checks, reward = [], 0.
    bodies, bounds = observation.get('bodies',{}), observation.get('bounds',{})
    for c in task['success']:
        kind, passed, measurement = c['kind'], None, None
        if kind == 'exists':
            passed = c['body'] in bodies
        elif kind == 'position':
            if c['body'] in bodies:
                measurement = math.sqrt(sum((x-y)**2 for x,y in zip(bodies[c['body']],c['target'])))
                passed = measurement <= c['tolerance']; reward -= measurement
            else: passed = False
        elif kind == 'above':
            b, support = bounds.get(c['body']), bounds.get(c['support'])
            if b and support and 'authored' not in observation.get('bounds_source',''):
                measurement = b['min'][2]-support['max'][2]
                passed = abs(measurement) <= c['tolerance'] and all(
                    support['min'][i]-c['tolerance'] <= b['min'][i] and b['max'][i] <= support['max'][i]+c['tolerance'] for i in (0,1))
        elif kind == 'max_speed' and 'qvel' in observation:
            measurement = max((abs(x) for x in observation['qvel']),default=0.)
            passed = measurement <= c['value']
        elif kind == 'max_penetration' and 'min_contact_distance' in observation:
            measurement = max(0.,-observation['min_contact_distance'])
            passed = measurement <= c['value']
        checks.append({'condition':c,'passed':passed,'measurement':measurement})
    success = False if any(c['passed'] is False for c in checks) else None if any(c['passed'] is None for c in checks) else True
    return {'success':success,'verdict':'pass' if success is True else 'fail' if success is False else 'inconclusive',
            'reward':float(reward + (1. if success else 0.)), 'checks':checks}
