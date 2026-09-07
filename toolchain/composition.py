"""Named scene edits compiled with MuJoCo's native attachment API.

Only validated local bundles and bounded JSON enter this module; never execute
model-generated XML or scripts. Existing bundles remain immutable.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import uuid
import xml.etree.ElementTree as ET

from loop_robot.toolchain.model_assets import snapshot, safe_path
from loop_robot.toolchain.scenes import compile_scene, default_scene, chair_scene, _vector

PROMPT = '''
仅返回以下组合编辑格式；不要添加objects、table、needs_expert等旧格式顶层字段：
{"base":"current","add":[{"name":"panda","kind":"asset","query":"franka_emika_panda","support":"table"}],"remove":[],"move":[],"assumptions":[],"unsupported":[]}
base=current保留所有现有物体；只有用户明确清空/创建全新场景才用empty。新增物品不要删除旧物体。
add元素严格使用字段 name,kind 及以下可选字段：
kind=wardrobe：固定尺寸双开门衣柜，带铰链和位置执行器，本地程序化模型而非扫描；kind=table：size=[长,宽,厚]、height；kind=chair：固定木椅（不是不支持的物品）；
kind=box/sphere/cylinder：box的size=[完整长,完整宽,完整高]；sphere的size=[半径]仅一个数；cylinder的size=[半径,完整高]仅两个数；可选mass；kind=asset：query（英文模型/物品检索名）或source（实际找到的公开GitHub blob/tree URL或model_library返回的官方Fuel source_url，不得编造）。
所有kind均支持position=[x,y,z]、yaw（弧度）、color=[r,g,b,a]；support为已存在或本轮先加入的支撑物name，或floor；默认floor。
不写position则根据支撑物自动居中/找空位并计算接触高度。写position时指定xy，z仍按支撑面修正。机械臂默认选Panda，写入assumptions；优先本地资产，没有自动搜索官方及公开模型。
桌椅和Panda示例：add=[{"name":"table","kind":"table"},{"name":"chair","kind":"chair","position":[-1,0,0]},{"name":"panda","kind":"asset","query":"franka_emika_panda","support":"table"}]。
桌上Panda不能写unsupported；关节与网格通过资产库导入，不用刚体替代。真实抓取策略/真实材料参数仍不能凭生成证明。
remove为要移除的精确name列表；move元素为{name,support,position?,yaw?}，移动保留资产与关节。已存在的物品不要重复add，用move。
用户说继续/生成/覆盖时执行最近明确请求，不再问确认。不编造路径、哈希、接触稳定或窗口结果。
'''


def validate_edit(edit):
    fields = {'base', 'add', 'remove', 'move', 'assumptions', 'unsupported'}
    if not isinstance(edit, dict): raise ValueError('Composition must be one JSON object')
    if set(edit)-fields: raise ValueError('Unknown composition fields: '+', '.join(sorted(set(edit)-fields))+'. Allowed: base,add,remove,move,assumptions,unsupported')
    if edit.get('base','current') not in ('current','empty'): raise ValueError('base must be the string current or empty, not a scene path or object')
    for key in ('add', 'remove', 'move', 'assumptions', 'unsupported'):
        if not isinstance(edit.get(key, []), list) or len(edit.get(key, [])) > 30:
            raise ValueError('Composition lists allow at most 30 entries')
    for key in ('remove', 'assumptions', 'unsupported'):
        if any(not isinstance(x, str) for x in edit.get(key, [])):
            raise ValueError('Composition explanations/names must be strings')
    if edit.get('unsupported'):
        raise ValueError('场景超出已实现范围: ' + '; '.join(edit['unsupported']))
    for item in edit.get('add', []) + edit.get('move', []):
        if not isinstance(item, dict) or set(item) - {'name','kind','query','source','support','position','yaw','size','height','mass','color'}:
            raise ValueError('Invalid composition object fields')
        if not isinstance(item.get('name'), str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}', item['name']):
            raise ValueError('Object name must be an ASCII identifier')
        if 'position' in item:
            _vector(item['position'], 3, -10, 10)
        _vector([item.get('yaw', 0)], 1, -math.tau, math.tau)
        if 'color' in item:
            _vector(item['color'], 4, 0, 1)
        kind=item.get('kind')
        if kind=='chair' and any(key in item for key in ('size','height')):
            raise ValueError('Fixed chair preset has fixed dimensions; use an asset for a differently shaped chair')
        if kind=='asset' and any(key in item for key in ('size','height','mass','color')):
            raise ValueError('Asset dimensions/material/dynamics come from the verified model; omit primitive-only size/height/mass/color fields')
        if 'support' in item and not isinstance(item['support'],str): raise ValueError('support must be an object name or floor')
        if item.get('support', 'floor') == item['name']:
            raise ValueError('An object cannot support itself')
    return edit


def load_spec(scene):
    import mujoco
    xml, assets, _ = snapshot(scene)
    return mujoco.MjSpec.from_string(xml.decode(), include=assets, assets=assets)


def state(spec):
    import mujoco
    model = spec.compile()
    data = mujoco.MjData(model)
    if model.nkey:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    from loop_robot.toolchain.viewer_motion import repair_invalid_home
    repair_invalid_home(mujoco,model,data)
    return model, data


def geom_bounds(model, data, geom):
    import mujoco
    import numpy as np
    typ = model.geom_type[geom]
    rotation = data.geom_xmat[geom].reshape(3, 3)
    center = data.geom_xpos[geom]
    if typ == mujoco.mjtGeom.mjGEOM_MESH:
        mesh = model.geom_dataid[geom]
        vertices = model.mesh_vert[model.mesh_vertadr[mesh]:model.mesh_vertadr[mesh]+model.mesh_vertnum[mesh]]
        points = vertices @ rotation.T + center
        return points.min(axis=0), points.max(axis=0)
    size = model.geom_size[geom].copy()
    if typ == mujoco.mjtGeom.mjGEOM_SPHERE:
        half = np.repeat(size[0], 3)
    elif typ in (mujoco.mjtGeom.mjGEOM_CYLINDER, mujoco.mjtGeom.mjGEOM_CAPSULE):
        half = np.array([size[0], size[0], size[1] + (size[0] if typ == mujoco.mjtGeom.mjGEOM_CAPSULE else 0)])
    else:
        half = size
    extent = abs(rotation) @ half
    return center - extent, center + extent


def surface(spec, name):
    import mujoco
    model, data = state(spec)
    if name == 'floor':
        return [0., 0., 0.], [-10., -10.], [10., 10.]
    for candidate in (name + '/chair_seat', name + '/table', name + '/surface', name + '_seat', name):
        gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, candidate)
        if gid >= 0 and model.geom_type[gid] == mujoco.mjtGeom.mjGEOM_BOX:
            low, high = geom_bounds(model, data, gid)
            # Only horizontal support surfaces have an unambiguous top plane.
            if abs(abs(data.geom_xmat[gid].reshape(3,3)[2,2]) - 1) > 1e-6:
                raise ValueError('Support surface must be horizontal')
            return [(low[0]+high[0])/2, (low[1]+high[1])/2, high[2]], low[:2].tolist(), high[:2].tolist()
    raise ValueError('No horizontal support surface found: ' + str(name))


def child_asset(scene, prefix):
    """Remove the library's stage, retain full robot/joints/actuators and assets."""
    import mujoco
    xml, assets, _ = snapshot(scene)
    child = mujoco.MjSpec.from_string(xml.decode(), include=assets, assets=assets)
    # A library scene may include its own floor/lights. Only attach its bodies.
    for item in list(child.worldbody.geoms) + list(child.worldbody.lights) + list(child.worldbody.cameras):
        child.delete(item)
    if not list(child.worldbody.bodies):
        raise ValueError('Asset has no attachable body; select a robot/object MJCF or mesh')
    # Namespace file names too, so two libraries with assets/base.obj cannot collide.
    child.compile()
    root = ET.fromstring(child.to_xml())
    packaged = {}
    for element in root.iter():
        name = element.get('file')
        if name:
            safe_path(name)
            data = assets.get(name)
            if data is None:
                matches = [value for key, value in assets.items() if key.endswith('/' + name) or key == name]
                if len(matches) != 1:
                    raise ValueError('Cannot resolve asset uniquely: ' + name)
                data = matches[0]
            path = prefix + '/' + name
            element.set('file', path)
            packaged[path] = data
    return mujoco.MjSpec.from_string(ET.tostring(root, encoding='unicode'), assets=packaged)


def primitive(item):
    import mujoco
    kind = item['kind']
    if kind == 'table':
        spec = default_scene(False)
        spec['table'] = {'size': item.get('size', [1.2,.8,.1]), 'height': item.get('height', .75), 'color': item.get('color', [.6,.45,.3,1])}
        root = ET.fromstring(compile_scene(spec))
    elif kind == 'chair':
        spec = chair_scene()
        spec['color'] = item.get('color', spec['color'])
        root = ET.fromstring(compile_scene(spec))
    elif kind == 'wardrobe':
        if any(k in item for k in ('size','height','mass')):
            raise ValueError('Wardrobe preset has fixed dimensions: 1.2 x 0.6 x 1.8 m')
        root = ET.Element('mujoco')
        ET.SubElement(root,'compiler',angle='radian')
        body = ET.SubElement(ET.SubElement(root,'worldbody'),'body',name='object')
        color=' '.join(map(str,item.get('color',[.55,.34,.17,1])))
        for name,pos,size in [('bottom','0 0 .03','.6 .3 .03'),('top','0 0 1.77','.6 .3 .03'),
                              ('back','0 .28 .9','.6 .02 .84'),('left','-.58 0 .9','.02 .3 .84'),
                              ('right','.58 0 .9','.02 .3 .84'),('shelf','0 0 .8','.56 .28 .02')]:
            ET.SubElement(body,'geom',name=name,type='box',pos=pos,size=size,rgba=color)
        actuator=ET.SubElement(root,'actuator')
        for name,x,dx,axis in [('left',-.56,.275,'0 0 -1'),('right',.56,-.275,'0 0 1')]:
            door=ET.SubElement(body,'body',name=name+'_door',pos=f'{x} -.31 .9')
            ET.SubElement(door,'joint',name=name+'_hinge',axis=axis,range='0 1.6',damping='3')
            ET.SubElement(door,'geom',name=name+'_panel',type='box',pos=f'{dx} 0 0',size='.275 .02 .84',mass='4',rgba='.7 .48 .25 1')
            ET.SubElement(door,'geom',name=name+'_handle',type='capsule',pos=f'{dx*1.7} -.055 0',size='.014 .07',mass='.1',rgba='.2 .2 .2 1')
            ET.SubElement(actuator,'position',name=name+'_open',joint=name+'_hinge',kp='40',kv='8',ctrlrange='0 1.6',forcerange='-20 20')
    elif kind in ('box', 'sphere', 'cylinder'):
        size = item.get('size', {'box':[.1,.1,.1], 'sphere':[.05], 'cylinder':[.05,.1]}[kind])
        expected={'box':3,'sphere':1,'cylinder':2}[kind]
        if not isinstance(size,list) or len(size)!=expected:
            raise ValueError(kind+'.size requires '+{'box':'[full_length,full_width,full_height]','sphere':'[radius] (one number)','cylinder':'[radius,full_height] (two numbers)'}[kind])
        _vector(size, expected, .001, 3)
        if kind == 'box': size = [x/2 for x in size]
        elif kind == 'cylinder': size = [size[0],size[1]/2]
        mass = item.get('mass', .1)
        _vector([mass], 1, .001, 100)
        root = ET.Element('mujoco')
        body = ET.SubElement(ET.SubElement(root,'worldbody'),'body',name='object')
        ET.SubElement(body,'freejoint',name='free')
        ET.SubElement(body,'geom', name='surface', type=kind, size=' '.join(map(str,size)), mass=str(mass), rgba=' '.join(map(str,item.get('color',[.8,.2,.15,1]))))
    else:
        raise ValueError('Unsupported object kind: ' + str(kind))
    world = root.find('worldbody')
    for element in list(world):
        if element.tag == 'light' or (element.tag == 'geom' and element.get('name') == 'floor'):
            world.remove(element)
    # Furniture world geoms become one named movable subtree (fixed in physics).
    if kind == 'table':
        body = ET.Element('body',name='object')
        for geom in list(world):
            world.remove(geom); body.append(geom)
        world.append(body)
    return mujoco.MjSpec.from_string(ET.tostring(root,encoding='unicode'))


def base_bounds(child):
    """Bounds of the mounting base, excluding articulated descendants."""
    import numpy as np
    model, data = state(child)
    roots = set(i for i in range(1,model.nbody) if model.body_parentid[i] == 0)
    fixed = set(roots)
    for i in range(1,model.nbody):
        if model.body_parentid[i] in fixed and model.body_jntnum[i] == 0:
            fixed.add(i)
    ids = [i for i in range(model.ngeom) if model.geom_bodyid[i] in fixed and (model.geom_contype[i] or model.geom_conaffinity[i])]
    if not ids:
        ids = [i for i in range(model.ngeom) if model.geom_bodyid[i] in fixed]
    if not ids:
        raise ValueError('Asset has no base geometry for support placement')
    bounds = [geom_bounds(model,data,i) for i in ids]
    return np.min([b[0] for b in bounds],axis=0), np.max([b[1] for b in bounds],axis=0)


def compose(edit, directory, current=None, resolve=None, description='', stop_event=None, on_event=None):
    import mujoco
    import numpy as np
    validate_edit(edit)
    def check_stop():
        if stop_event and stop_event.is_set(): raise RuntimeError('Master stopped')
    check_stop()
    parent = load_spec(current) if current and edit.get('base','current') == 'current' else mujoco.MjSpec.from_string(
        '<mujoco model="loop_composed"><option timestep=".002" integrator="implicitfast"/><worldbody><light pos="0 0 3"/><geom name="floor" type="plane" size="3 3 .1" rgba=".3 .3 .3 1"/></worldbody></mujoco>')
    parent.copy_during_attach = True
    metadata = {}
    if current and edit.get('base','current') == 'current':
        report = Path(current).with_name('report.json')
        if report.exists(): metadata = json.loads(report.read_text()).get('objects',{})
    metadata = dict(metadata)
    if current and not metadata and edit.get('base','current')=='current':
        old=Path(current).with_name('scene.json')
        if old.exists():
            legacy=json.loads(old.read_text())
            metadata={obj['name']:{'kind':obj.get('shape'),'support':'table','position':obj.get('position')} for obj in legacy.get('objects',[])}
            if legacy.get('preset')=='chair': metadata['chair']={'kind':'chair','support':'floor'}
            if legacy.get('preset')!='chair' or legacy.get('include_table'): metadata['table']={'kind':'table','support':'floor'}
    def remove(name):
        matches = [b for b in parent.worldbody.bodies if b.name == name or b.name.startswith(name+'/')]
        geoms = [g for g in parent.worldbody.geoms if g.name == name or g.name.startswith(name+'_')]
        if not matches and not geoms: raise ValueError('Object not found: '+name)
        for obj in matches+geoms: parent.delete(obj)
        metadata.pop(name,None)
    for name in edit.get('remove',[]):
        if any(obj.get('support')==name and key not in edit.get('remove',[]) for key,obj in metadata.items()):
            raise ValueError('Remove supported objects before removing support: '+name)
        remove(name)
    # Store all home poses by joint name; attachment key order is not a home-pose policy.
    homes, controls = {}, {}
    def remember(spec, prefix=''):
        model,data=state(spec)
        for i in range(model.njnt):
            name=mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_JOINT,i)
            end=model.jnt_qposadr[i+1] if i+1<model.njnt else model.nq
            if name and not (prefix and model.jnt_type[i]==mujoco.mjtJoint.mjJNT_FREE): homes[prefix+name]=data.qpos[model.jnt_qposadr[i]:end].copy()
        for i in range(model.nu):
            name=mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_ACTUATOR,i)
            if name: controls[prefix+name]=float(data.ctrl[i])
    remember(parent)
    for item in edit.get('add',[]):
        check_stop()
        name=item['name']; prefix=name+'/'
        if any(b.name==name or b.name.startswith(prefix) for b in parent.worldbody.bodies) or parent.geom(name):
            raise ValueError('Object already exists; use move or remove: '+name)
        source = {}
        if item.get('kind')=='asset':
            if resolve is None: raise ValueError('Asset resolver unavailable')
            if on_event: on_event('Scene asset', 'Resolving '+str(item.get('query') or item.get('source')))
            source=resolve(item.get('query',name),item.get('source'))
            check_stop()
            child=child_asset(source['scene'],name)
        else: child=primitive(item)
        low,high=base_bounds(child)
        center,smin,smax=surface(parent,item.get('support','floor'))
        position=list(item.get('position',center))
        yaw=item.get('yaw',0); c,s=math.cos(yaw),math.sin(yaw)
        rot=np.array([[c,-s],[s,c]])
        corners=np.array([[x,y] for x in (low[0],high[0]) for y in (low[1],high[1])]) @ rot.T
        # Search unoccupied mounting positions when no exact XY was requested.
        candidates=[position[:2]]
        if 'position' not in item and item.get('support','floor')!='floor':
            candidates += [[x,y] for x in np.linspace(smin[0]-corners[:,0].min(),smax[0]-corners[:,0].max(),5)
                            for y in np.linspace(smin[1]-corners[:,1].min(),smax[1]-corners[:,1].max(),5)]
        chosen=None
        for xy in candidates:
            lo=corners.min(axis=0)+xy; hi=corners.max(axis=0)+xy
            if np.any(lo < np.array(smin)-1e-5) or np.any(hi > np.array(smax)+1e-5): continue
            if any(obj.get('support')==item.get('support','floor') and 'footprint' in obj and
                   all(lo[i]<obj['footprint'][1][i]-1e-4 and hi[i]>obj['footprint'][0][i]+1e-4 for i in (0,1)) for obj in metadata.values()): continue
            chosen=(xy,lo,hi);break
        if chosen is None: raise ValueError('No free support area for '+name+'; choose another support or position')
        position=[*map(float,chosen[0]),float(center[2]-low[2])]
        frame=parent.worldbody.add_frame(pos=position,quat=[math.cos(yaw/2),0,0,math.sin(yaw/2)])
        remember(child,prefix)
        for key in list(child.keys): child.delete(key)
        child.nkey=0
        parent.attach(child,frame=frame,prefix=prefix)
        metadata[name]={'kind':item.get('kind'),'support':item.get('support','floor'),'position':position,'yaw':yaw,
                        'footprint':[chosen[1].tolist(),chosen[2].tolist()], 'base_bottom_z':float(center[2]),
                        'support_top_z':float(center[2]),'source':{k:v for k,v in source.items() if k in ('source_url','commit','model','repository','archive_sha256','license','license_url','assumptions')},
                        'mounting':('free' if any(j.type==mujoco.mjtJoint.mjJNT_FREE for b in child.worldbody.bodies for j in b.joints) else 'fixed') if item.get('kind')=='asset' else 'scene_geometry'}
    if edit.get('move'):
        parent.compile()
        parent=mujoco.MjSpec.from_string(parent.to_xml(),assets=dict(parent.assets))
    for item in edit.get('move',[]):
        name=item['name']
        if any(obj.get('support')==name for obj in metadata.values()):
            raise ValueError('Move supported objects first; support is occupied: '+name)
        roots=[b for b in parent.worldbody.bodies if b.name==name or b.name.startswith(name+'/')]
        if len(roots)!=1: raise ValueError('Move requires one named object root: '+name)
        obj=roots[0]
        center,smin,smax=surface(parent,item.get('support','floor'))
        model,data=state(parent)
        bid=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_BODY,obj.name)
        fixed={bid}
        for i in range(1,model.nbody):
            if model.body_parentid[i] in fixed and model.body_jntnum[i]==0: fixed.add(i)
        ids=[i for i in range(model.ngeom) if model.geom_bodyid[i] in fixed and (model.geom_contype[i] or model.geom_conaffinity[i])]
        if not ids: raise ValueError('Object base geometry unavailable for move')
        bounds=[geom_bounds(model,data,i) for i in ids]
        low=np.min([b[0] for b in bounds],axis=0);high=np.max([b[1] for b in bounds],axis=0)
        position=list(item.get('position',center));position[2]=float(data.xpos[bid][2]+center[2]-low[2])
        yaw=item.get('yaw',metadata.get(name,{}).get('yaw',0))
        delta_yaw=yaw-metadata.get(name,{}).get('yaw',0)
        c,s=math.cos(delta_yaw),math.sin(delta_yaw)
        corners=np.array([[x,y] for x in (low[0],high[0]) for y in (low[1],high[1])])-data.xpos[bid][:2]
        corners=corners @ np.array([[c,-s],[s,c]]).T+position[:2]
        lo,hi=corners.min(axis=0),corners.max(axis=0)
        if np.any(lo<np.array(smin)-1e-5) or np.any(hi>np.array(smax)+1e-5): raise ValueError('Moved base exceeds support bounds')
        if any(key!=name and other.get('support')==item.get('support','floor') and 'footprint' in other and
               all(lo[i]<other['footprint'][1][i]-1e-4 and hi[i]>other['footprint'][0][i]+1e-4 for i in (0,1)) for key,other in metadata.items()):
            raise ValueError('Moved base overlaps another object')
        obj.pos=position
        obj.quat=[math.cos(yaw/2),0,0,math.sin(yaw/2)]
        for joint in obj.joints:
            if joint.type==mujoco.mjtJoint.mjJNT_FREE and joint.name:
                homes[joint.name]=np.array(position+list(obj.quat))
        metadata.setdefault(name,{}).update(position=position,yaw=yaw,support=item.get('support','floor'),support_top_z=float(center[2]),base_bottom_z=float(center[2]),footprint=[lo.tolist(),hi.tolist()])
    check_stop()
    for key in list(parent.keys): parent.delete(key)
    model=parent.compile();data=mujoco.MjData(model)
    for i in range(model.njnt):
        name=mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_JOINT,i)
        if name in homes: data.qpos[model.jnt_qposadr[i]:model.jnt_qposadr[i]+len(homes[name])]=homes[name]
    for i in range(model.nu):
        name=mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_ACTUATOR,i)
        if name in controls: data.ctrl[i]=controls[name]
    mujoco.mj_forward(model,data)
    if not np.isfinite(data.qpos).all() or not np.isfinite(data.qacc).all(): raise ValueError('Invalid composed state')
    parent.nkey=1
    parent.add_key(name='scene_home',qpos=data.qpos,ctrl=data.ctrl)
    parent.compile()
    xml=parent.to_xml()
    # Serialization flattens includes; old scene.xml must never overwrite the new root.
    assets={name:data for name,data in parent.assets.items() if not name.lower().endswith(".xml")}
    # Compile the exact serialized bundle, then smoke-test a copy without changing home.
    verified=mujoco.MjModel.from_xml_string(xml,assets=assets)
    smoke=mujoco.MjData(verified);mujoco.mj_resetDataKeyframe(verified,smoke,0)
    for _ in range(100):
        mujoco.mj_step(verified,smoke)
        if not np.isfinite(smoke.qpos).all() or np.any(smoke.warning.number): raise ValueError('Composed physics smoke failed')
    check_stop()
    output=Path(directory)/uuid.uuid4().hex;output.mkdir(parents=True)
    try:
        files={**assets,'scene.xml':xml.encode()}
        hashes={}
        for name,data_bytes in files.items():
            safe_path(name);target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data_bytes)
            hashes[name]=hashlib.sha256(data_bytes).hexdigest()
        (output/'.loop-assets.json').write_text(json.dumps({'files':hashes,'kind':'composed'},indent=2))
        _,_,digest=snapshot(output/'scene.xml')
        report={'scene':str((output/'scene.xml').resolve()),'report':str((output/'report.json').resolve()),'description':description,
                'model':'scene-composer','scene_sha256':digest,'objects':metadata,'assumptions':edit.get('assumptions',[]),
                'validation':{'compiled':True,'physics_smoke':'pass','semantic_verdict':'unverified','task_success':'not_evaluated'},
                'model_bodies':[mujoco.mj_id2name(verified,mujoco.mjtObj.mjOBJ_BODY,i) for i in range(1,verified.nbody)],
                'joints':verified.njnt,'actuators':verified.nu}
        (output/'composition.json').write_text(json.dumps(edit,ensure_ascii=False,indent=2))
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        return report
    except Exception:
        shutil.rmtree(output);raise
