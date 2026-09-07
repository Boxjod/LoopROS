"""Native tool schemas and permission entry shared by the optional MCP server."""
from pathlib import Path

from loop_robot.terminal.skills import schema

INSTANCE={'type':'string','description':'Exact live instance ID from sim_create; instances are owned by this process'}
CAMERAS={'type':'array','items':{'type':'string'},'minItems':1,'maxItems':8,'uniqueItems':True}
ACTION={'type':'array','items':{'type':'number'},'description':'Exact action_space order/units from sim_inspect; never assume joint positions for MuJoCo ctrl'}
CAMERA={'type':'object','properties':{
    'name':{'type':'string'},'parent':{'type':'string','description':'world, MuJoCo body name, or absolute Isaac USD parent prim'},
    'position':{'type':'array','items':{'type':'number'},'minItems':3,'maxItems':3,'description':'Metres relative to parent'},
    'quaternion':{'type':'array','items':{'type':'number'},'minItems':4,'maxItems':4,'description':'wxyz local orientation; +X right +Y up -Z forward'},
    'width':{'type':'integer','minimum':16,'maximum':1024},'height':{'type':'integer','minimum':16,'maximum':1024},
    'fovy':{'type':'number'},'near':{'type':'number'},'far':{'type':'number'}},'required':['name','position','quaternion'],'additionalProperties':False}
TOOLS=[
    schema('sim_create','Create an owned headless MuJoCo/Isaac workbench instance. No GUI restart. Isaac requires an operator-configured running bridge.',
           {'backend':{'type':'string','enum':['mujoco','isaac']},'scene':{'type':'string','description':'Optional local MJCF/USD path; USD path is on Isaac host'}},['backend']),
    schema('sim_list','List workbench instances owned by this process (not other GUI simulators).',{},[]),
    schema('sim_inspect','Read physics state, camera inventory, action units/order and measured task evaluation.',{'instance':INSTANCE},['instance']),
    schema('sim_edit','Add box or local robot asset. Box size is full XYZ metres, mass=0 static. Robot uses local MJCF in MuJoCo, USD in Isaac. Isaac edits reset its owned world.',
        {'instance':INSTANCE,'operation':{'type':'string','enum':['box','robot','asset','move','remove']},'config':{'type':'object','properties':{
            'name':{'type':'string'},'path':{'type':'string'},'position':{'type':'array','items':{'type':'number'}},
            'size':{'type':'array','items':{'type':'number'}},'mass':{'type':'number'},'color':{'type':'array','items':{'type':'number'}}},'required':['name'],'additionalProperties':False}},['instance','operation','config']),
    schema('sim_convert','Convert local URDF/MJCF to a new USD file on the Isaac host using its installed importer. Preserve defaults; report articulation/joints. Not proof of equivalent physics.',
        {'instance':INSTANCE,'source':{'type':'string'},'format':{'type':'string','enum':['urdf','mjcf']},'output':{'type':'string'}},['instance','source','format','output']),
    schema('sim_camera','Create fixed/world or attached/wrist camera with calibrated RGB, depth and segmentation. Local OpenGL camera axes; querying/capturing does not advance physics.',
        {'instance':INSTANCE,'config':CAMERA},['instance','config']),
    schema('sim_reset','Reset owned instance to its initial state. Seed recorded; no implicit domain randomization.',
        {'instance':INSTANCE,'seed':{'type':'integer','minimum':0}},['instance']),
    schema('sim_step','Apply controls and advance a bounded number of physics steps; return observed state and task reward/termination.',
        {'instance':INSTANCE,'action':ACTION,'steps':{'type':'integer','minimum':1,'maximum':1000}},['instance','action']),
    schema('sim_capture','Save synchronized RGB PNG + RGB/depth/segmentation NPZ and calibration, state, scene identity. Image statistics are not task success.',
        {'instance':INSTANCE,'cameras':CAMERAS},['instance','cameras']),
    schema('sim_task','Define task/variation/seed/horizon and measured success conditions. Supports exists(body), position(body,target,tolerance), above(body,support,tolerance), max_speed(value), max_penetration(value). Unavailable measurements are inconclusive.',
        {'instance':INSTANCE,'task':{'type':'object','properties':{
            'name':{'type':'string'},'description':{'type':'string'},'variation':{'type':'integer','minimum':0},
            'seed':{'type':'integer','minimum':0},'horizon':{'type':'integer','minimum':1,'maximum':10000},
            'success':{'type':'array','minItems':1,'items':{'type':'object','properties':{
                'kind':{'type':'string','enum':['exists','position','above','max_speed','max_penetration']},'body':{'type':'string'},'support':{'type':'string'},
                'target':{'type':'array','items':{'type':'number'}},'tolerance':{'type':'number','minimum':0},'value':{'type':'number','minimum':0}},'required':['kind'],'additionalProperties':False}}},
            'required':['name','success'],'additionalProperties':False}},['instance','task']),
    schema('sim_record','Record bounded action sequence from current state into task/variation episode HDF5 with multi-camera observations and ACT-shaped action data. Requires sim_task; actual success retained, incomplete episodes rejected by loader. Does not train.',
        {'instance':INSTANCE,'actions':{'type':'array','items':ACTION,'minItems':1,'maxItems':1000},'cameras':CAMERAS,
         'steps':{'type':'integer','minimum':1,'maximum':1000}},['instance','actions','cameras']),
    schema('sim_close','Close an owned headless workbench instance; does not close other GUI windows.',{'instance':INSTANCE},['instance'])]
NAMES={t['function']['name'] for t in TOOLS}
READ_NAMES={'sim_list','sim_inspect'}


def call_service(service,permissions,name,args):
    tool=next((t['function'] for t in TOOLS if t['function']['name']==name),None)
    if not tool or not isinstance(args,dict): raise ValueError('Unknown simulation tool or invalid arguments')
    params=tool['parameters']
    if set(args)-set(params['properties']) or not set(params['required'])<=set(args): raise ValueError('Invalid simulation arguments')
    permissions.check(name,args)
    return service.call(name,args)


def call(app,name,args):
    if not hasattr(app,'simulation_workbench'):
        from loop_robot.toolchain.simulation import SimulationWorkbench
        from loop_robot.terminal.home import loop_home
        app.simulation_workbench=SimulationWorkbench(app.state_dir/'simulation',loop_home()/'isaac-bridge.json',
                                                    cancelled=lambda:app.stop_event.is_set())
    return call_service(app.simulation_workbench,app.permissions,name,args)
