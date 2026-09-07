"""Isaac runtime adapter, imported only after SimulationApp has started."""
import hashlib
import math
from pathlib import Path

from toolchain.sim_cameras import camera_config, calibration, identifier, rotation, vector


class IsaacSimulation:
    backend = 'isaac'

    def __init__(self, app, scene=None):
        import numpy as np
        import omni.usd
        from isaacsim.core.api import World
        from isaacsim.core.utils.stage import create_new_stage, open_stage
        from pxr import UsdLux, Gf
        self.np,self.app=np,app
        World.clear_instance()
        if scene:
            if not Path(scene).is_file(): raise ValueError('USD scene must exist on the Isaac host')
            if not open_stage(str(Path(scene).resolve())): raise RuntimeError('Could not open USD stage')
        else: create_new_stage()
        self.stage=omni.usd.get_context().get_stage()
        self.world=World(stage_units_in_meters=1., physics_dt=1/120.,rendering_dt=1/60.)
        if not scene:
            self.world.scene.add_ground_plane(size=10., color=np.array([.3,.3,.3]))
            light=UsdLux.DomeLight.Define(self.stage,'/World/LoopLight')
            light.CreateIntensityAttr(800.)
        self.robots,self.objects,self.cameras,self.sensors,self.annotators={},{},{},{},{}
        self.time=0.;self.last_action=[];self.revision=0;self.seed=0
        try:
            from isaacsim.core.version import get_version
            self.version=str(get_version()[0])
        except ImportError: self.version='unknown'
        self.world.reset();self.world.pause()
        self.scene_hash=hashlib.sha256(self.stage.GetRootLayer().ExportToString().encode()).hexdigest()

    def _reset_world(self):
        self.world.reset();self.world.pause();self.time=0.
        for robot in self.robots.values(): robot.initialize()
        self.last_action=self._joint_state()[0]

    def edit(self, operation, config):
        import numpy as np
        name=identifier(config.get('name'));path='/World/'+name
        if operation in ('move','remove'):
            if name not in self.objects and name not in self.robots: raise ValueError('Unknown owned object')
            if operation=='move':
                if set(config)-{'name','position'}: raise ValueError('move accepts name and world position')
                obj=self.objects.get(name) or self.robots.get(name)
                obj.set_world_pose(position=np.array(vector(config.get('position'),3,'position')))
            else:
                if set(config)!={'name'}: raise ValueError('remove accepts name only')
                if any(s.prim_path.startswith(path+'/') for s in self.sensors.values()):
                    raise ValueError('Object has attached cameras; close/rebuild the instance instead of leaving stale sensors')
                self.world.scene.remove_object(name)
                self.objects.pop(name,None);self.robots.pop(name,None)
            self.scene_hash=hashlib.sha256(self.stage.GetRootLayer().ExportToString().encode()).hexdigest()
            return self.inspect()
        if self.stage.GetPrimAtPath(path).IsValid(): raise ValueError('Prim already exists')
        if operation=='box':
            from isaacsim.core.api.objects import DynamicCuboid, FixedCuboid
            if set(config)-{'name','position','size','mass','color'}: raise ValueError('Unknown box fields')
            size=vector(config.get('size',[.1,.1,.1]),3,'size')
            position=vector(config.get('position',[0,0,.5]),3,'position')
            color=vector(config.get('color',[.7,.4,.2,1]),4,'color')
            mass=config.get('mass',0.)
            if not isinstance(mass,(float,int)) or not math.isfinite(mass) or mass<0 or min(size)<=0 or any(x<0 or x>1 for x in color):
                raise ValueError('Invalid size/mass/color')
            cls=DynamicCuboid if mass>0 else FixedCuboid
            obj=cls(prim_path=path,name=name,position=np.array(position),size=1.,scale=np.array(size),color=np.array(color[:3]),**({'mass':mass} if mass>0 else {}))
            from pxr import Gf
            # Isaac 4.5 authors scaled extents; USD extents must be local.
            obj.geom.GetExtentAttr().Set([Gf.Vec3f(-.5), Gf.Vec3f(.5)])
            self.world.scene.add(obj);self.objects[name]=obj
        elif operation in ('robot','asset'):
            from pxr import Usd, UsdPhysics
            from isaacsim.core.prims import SingleArticulation
            from isaacsim.core.prims import SingleXFormPrim
            if set(config)-{'name','path','position'} or not config.get('path'): raise ValueError('robot requires local USD path')
            source=Path(config['path']).resolve()
            if not source.is_file() or source.suffix.lower() not in ('.usd','.usda','.usdc'):
                raise ValueError('Import a converted USD robot file on the Isaac host')
            asset=Usd.Stage.Open(str(source))
            root=asset.GetDefaultPrim()
            if not root.IsValid():
                roots=asset.GetPseudoRoot().GetChildren()
                if len(roots)!=1: raise ValueError('USD has no unambiguous default prim')
                root=roots[0]
            if operation=='robot' and not any(p.HasAPI(UsdPhysics.ArticulationRootAPI) for p in Usd.PrimRange(root)):
                raise ValueError('USD asset has no articulation root; use asset for non-robot geometry')
            prim=self.stage.DefinePrim(path,'Xform')
            prim.GetReferences().AddReference(str(source),str(root.GetPath()))
            position=vector(config.get('position',[0,0,0]),3,'position')
            from pxr import Gf
            if operation=='robot':
                for child in Usd.PrimRange(prim):
                    if child.IsA(UsdPhysics.FixedJoint):
                        joint=UsdPhysics.FixedJoint(child)
                        if not joint.GetBody0Rel().GetTargets():
                            joint.GetLocalPos0Attr().Set(Gf.Vec3f(*position))
            cls=SingleArticulation if operation=='robot' else SingleXFormPrim
            obj=cls(prim_path=path,name=name,position=np.array(vector(config.get('position',[0,0,0]),3,'position')))
            obj.set_default_state(position=np.array(position))
            self.world.scene.add(obj)
            (self.robots if operation=='robot' else self.objects)[name]=obj
        else: raise ValueError('Supported edits: box, robot')
        from isaacsim.core.utils.semantics import add_update_semantics
        add_update_semantics(self.stage.GetPrimAtPath(path),name)
        self._reset_world();self.revision+=1
        self.scene_hash=hashlib.sha256(self.stage.GetRootLayer().ExportToString().encode()).hexdigest()
        return {**self.inspect(),'state_reset':True}

    def camera(self, config):
        import omni.replicator.core as rep
        from isaacsim.sensors.camera import Camera
        from pxr import Gf
        c=camera_config(config)
        if c['name'] in self.cameras: raise ValueError('Camera already exists')
        parent='/World' if c['parent']=='world' else c['parent']
        if not self.stage.GetPrimAtPath(parent).IsValid(): raise ValueError('Unknown camera parent prim')
        path=parent+'/'+c['name']
        if self.stage.GetPrimAtPath(path).IsValid(): raise ValueError('Camera prim already exists')
        camera=Camera(prim_path=path,resolution=(c['width'],c['height']))
        camera.set_local_pose(translation=self.np.array(c['position']),orientation=self.np.array(c['quaternion']),camera_axes='usd')
        prim=self.stage.GetPrimAtPath(path)
        # USD aperture/focal length share units; square pixels and explicit vertical FoV.
        focal=24.
        vertical=2*focal*math.tan(math.radians(c['fovy'])/2)
        prim.GetAttribute('focalLength').Set(focal)
        prim.GetAttribute('verticalAperture').Set(vertical)
        prim.GetAttribute('horizontalAperture').Set(vertical*c['width']/c['height'])
        prim.GetAttribute('clippingRange').Set(Gf.Vec2f(c['near'],c['far']))
        camera.initialize()
        product=camera.get_render_product_path()
        annotators={}
        for key,kind in [('rgb','rgb'),('depth','distance_to_image_plane'),('segmentation','instance_segmentation')]:
            ann=rep.AnnotatorRegistry.get_annotator(kind)
            ann.attach([product]);annotators[key]=ann
        self.cameras[c['name']]=c;self.sensors[c['name']]=camera;self.annotators[c['name']]=annotators
        self.revision+=1
        self.scene_hash=hashlib.sha256(self.stage.GetRootLayer().ExportToString().encode()).hexdigest()
        return {**c,'prim_path':path}

    def convert(self,source,format,output):
        import omni.kit.commands
        from isaacsim.core.utils.extensions import enable_extension
        from pxr import Usd,UsdPhysics
        src,dest=Path(source).resolve(),Path(output).resolve()
        if format not in ('urdf','mjcf') or not src.is_file(): raise ValueError('Existing URDF/MJCF source required')
        if dest.exists() or dest.suffix.lower() not in ('.usd','.usda','.usdc'):
            raise ValueError('Choose a new USD output path; existing files are never overwritten')
        enable_extension('isaacsim.asset.importer.'+format)
        dest.parent.mkdir(parents=True,exist_ok=True)
        ok,config=omni.kit.commands.execute(format.upper()+'CreateImportConfig')
        if not ok: raise RuntimeError('Installed Isaac importer command unavailable; check version-specific API')
        # Keep upstream defaults; do not silently override masses, drives or merge joints.
        if format=='urdf':
            ok,result=omni.kit.commands.execute('URDFParseAndImportFile',urdf_path=str(src),import_config=config,dest_path=str(dest))
        else:
            ok,result=omni.kit.commands.execute('MJCFCreateAsset',mjcf_path=str(src),import_config=config,prim_path='/Robot',dest_path=str(dest))
        if not ok or not dest.is_file(): raise RuntimeError('Importer did not produce a USD file')
        stage=Usd.Stage.Open(str(dest))
        if stage is None: raise RuntimeError('Converted USD cannot be opened')
        if not stage.GetDefaultPrim().IsValid():
            roots=stage.GetPseudoRoot().GetChildren()
            if len(roots)!=1: raise RuntimeError('Converted asset lacks an unambiguous root')
            stage.SetDefaultPrim(roots[0]);stage.GetRootLayer().Save()
        articulations=[str(p.GetPath()) for p in stage.Traverse() if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
        joints=[str(p.GetPath()) for p in stage.Traverse() if p.IsA(UsdPhysics.Joint)]
        return {'source':str(src),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
                'output':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
                'articulations':articulations,'joints':joints,'version':self.version,
                'validation':'USD readable; dynamics and control equivalence not evaluated'}

    def _joint_state(self):
        qpos,qvel,names,bounds=[],[],[],[]
        for name,robot in self.robots.items():
            qpos.extend(robot.get_joint_positions().tolist());qvel.extend(robot.get_joint_velocities().tolist())
            names.extend(name+'/'+n for n in robot.dof_names)
            limits=robot.dof_properties
            for lo,hi in zip(limits['lower'],limits['upper']):
                bounds.append([float(lo),float(hi)] if math.isfinite(lo) and math.isfinite(hi) and lo<hi else None)
        return qpos,qvel,names,bounds

    def inspect(self):
        from pxr import UsdGeom, Usd
        qpos,qvel,names,bounds=self._joint_state()
        bodies={};boxes={}
        cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render])
        for name,obj in {**self.objects,**self.robots}.items():
            position,_=obj.get_world_pose();bodies[name]=position.tolist()
            bound=cache.ComputeWorldBound(self.stage.GetPrimAtPath(obj.prim_path)).ComputeAlignedBox()
            if not bound.IsEmpty(): boxes[name]={'min':list(bound.GetMin()),'max':list(bound.GetMax())}
        return {'backend':'isaac','version':self.version,'time':self.time,'scene_sha256':self.scene_hash,'seed':self.seed,
                'qpos':qpos,'qvel':qvel,'action':list(self.last_action),
                'action_space':{'kind':'joint_position_target','names':names,'bounds':bounds},
                'bodies':bodies,'bounds':boxes,'bounds_source':'USD authored transforms; not a contact measurement',
                'cameras':self.cameras,'state_source':'physics joint/body wrappers','timeline':'paused',
                'unsupported':['contact penetration query','automatic RL training','MJCF direct import; convert to USD first']}

    def reset(self, seed=0):
        if type(seed) is not int or seed<0: raise ValueError('Invalid seed')
        self.seed=seed
        self._reset_world()
        return self.inspect()

    def step(self, action, steps=1):
        from isaacsim.core.utils.types import ArticulationAction
        qpos,_,_,bounds=self._joint_state()
        values=vector(action,len(qpos),'joint position targets')
        if type(steps) is not int or not 1<=steps<=1000: raise ValueError('steps must be 1..1000')
        for v,b in zip(values,bounds):
            if b and not b[0]<=v<=b[1]: raise ValueError('Joint target outside limit')
        offset=0
        for robot in self.robots.values():
            count=robot.num_dof
            robot.get_articulation_controller().apply_action(ArticulationAction(joint_positions=self.np.array(values[offset:offset+count])))
            offset+=count
        self.world.play()
        try:
            for _ in range(steps): self.world.step(render=False)
        finally: self.world.pause()
        self.time+=steps*self.world.get_physics_dt();self.last_action=values
        state=self.inspect()
        if not self.np.isfinite(state['qpos']).all(): raise RuntimeError('Nonfinite physics state')
        return state

    def capture(self,names):
        if not isinstance(names,list) or not 1<=len(names)<=8 or len(set(names))!=len(names) or any(n not in self.cameras for n in names):
            raise ValueError('Select 1..8 existing unique cameras')
        # Rendering without world.step does not advance physical time.
        import omni.replicator.core as rep
        rep.orchestrator.step(delta_time=0.0, rt_subframes=8, pause_timeline=True)
        frames={}
        for name in names:
            c=self.cameras[name];a=self.annotators[name]
            rgb=self.np.asarray(a['rgb'].get_data())
            depth=self.np.asarray(a['depth'].get_data())
            seg=a['segmentation'].get_data()
            mask=self.np.asarray(seg['data'] if isinstance(seg,dict) else seg)
            if rgb.shape[:2]!=(c['height'],c['width']) or depth.size!=c['height']*c['width']:
                raise RuntimeError('Camera frame not ready or dimensions differ; no successful capture')
            pos,quat=self.sensors[name].get_world_pose(camera_axes='usd')
            cal=calibration(c,pos,rotation(quat))
            cal['intrinsics']=self.sensors[name].get_intrinsics_matrix().tolist()
            frames[name]={'rgb':rgb[...,:3].copy(),'depth':depth.reshape(c['height'],c['width']).copy(),
                'segmentation':mask.copy(),'calibration':cal,'labels':seg.get('info',{}).get('idToLabels',{}) if isinstance(seg,dict) else {}}
        return frames

    def close(self):
        for name,anns in self.annotators.items():
            product=self.sensors[name].get_render_product_path()
            for ann in anns.values(): ann.detach([product])
        self.world.stop()
        self.cameras.clear();self.sensors.clear();self.annotators.clear()
