"""Owned, headless MuJoCo workbench. Does not attach to or restart the GUI."""
import hashlib
from pathlib import Path

from loop_robot.toolchain.sim_cameras import camera_config, calibration, identifier, vector

EMPTY = '<mujoco><option timestep="0.002"/><visual><global offwidth="1024" offheight="1024"/></visual><worldbody><light pos="0 0 3"/><geom name="floor" type="plane" size="5 5 .1" rgba=".3 .3 .3 1"/></worldbody></mujoco>'


class MujocoSimulation:
    backend = 'mujoco'

    def __init__(self, scene=None):
        import mujoco
        import numpy as np
        self.mj, self.np = mujoco, np
        if scene:
            from loop_robot.toolchain.model_assets import snapshot
            if (Path(scene).parent/'.loop-assets.json').exists():
                xml, assets, _ = snapshot(scene)
                self.spec = mujoco.MjSpec.from_string(xml.decode(), include=assets, assets=assets)
            else:
                self.spec = mujoco.MjSpec.from_file(str(Path(scene).resolve()))
        else:
            self.spec = mujoco.MjSpec.from_string(EMPTY)
        self.spec.visual.global_.offwidth = 1024
        self.spec.visual.global_.offheight = 1024
        self.model = self.spec.compile()
        self.data = mujoco.MjData(self.model)
        self.cameras, self.renderers = {}, {}
        for i in range(self.model.ncam):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_CAMERA, i)
            if name and name.replace('_', '').isalnum() and name[0].isalpha():
                self.cameras[name] = camera_config({'name': name, 'fovy': float(self.model.cam_fovy[i])})
        self.reset()

    def _commit(self, spec):
        model = spec.compile()
        data = self.mj.MjData(model)
        if model.nkey:
            self.mj.mj_resetDataKeyframe(model, data, 0)
        # Preserve runtime values by names, not by potentially shifted addresses.
        for i in range(model.njnt):
            name = self.mj.mj_id2name(model, self.mj.mjtObj.mjOBJ_JOINT, i)
            old = self.mj.mj_name2id(self.model, self.mj.mjtObj.mjOBJ_JOINT, name) if name else -1
            if old >= 0 and model.jnt_type[i] == self.model.jnt_type[old]:
                data.joint(i).qpos[:] = self.data.joint(old).qpos
                data.joint(i).qvel[:] = self.data.joint(old).qvel
        for i in range(model.nu):
            name = self.mj.mj_id2name(model, self.mj.mjtObj.mjOBJ_ACTUATOR, i)
            old = self.mj.mj_name2id(self.model, self.mj.mjtObj.mjOBJ_ACTUATOR, name) if name else -1
            if old >= 0:
                data.ctrl[i] = self.data.ctrl[old]
        data.time = self.data.time
        self.mj.mj_forward(model, data)
        if self.cameras:
            config = next(iter(self.cameras.values()))
            model.vis.map.znear = config['near']/model.stat.extent
            model.vis.map.zfar = config['far']/model.stat.extent
        self.close_renderers()
        self.spec, self.model, self.data = spec, model, data

    def edit(self, operation, config):
        spec = self.spec.copy()
        name = identifier(config.get('name'))
        if operation in ('move','remove'):
            body=spec.body(name)
            if body is None: raise ValueError('Unknown body; use its exact name')
            if operation=='remove':
                if set(config)!={'name'}: raise ValueError('remove accepts name only')
                if any(c['parent']==name for c in self.cameras.values()): raise ValueError('Body has an attached camera')
                spec.delete(body);self._commit(spec)
            else:
                if set(config)-{'name','position'}: raise ValueError('move accepts name and position')
                pos=vector(config.get('position'),3,'position');body.pos=pos
                self._commit(spec)
                live=self.model.body(name)
                if live.jntnum and self.model.jnt_type[live.jntadr[0]]==self.mj.mjtJoint.mjJNT_FREE:
                    self.data.joint(live.jntadr[0]).qpos[:3]=pos
                self.mj.mj_forward(self.model,self.data)
            return self.inspect()
        if operation == 'box':
            if set(config)-{'name','position','size','mass','color'}:
                raise ValueError('Unknown box fields')
            size = vector(config.get('size', [.1,.1,.1]), 3, 'full size')
            pos = vector(config.get('position', [0,0,.5]), 3, 'position')
            rgba = vector(config.get('color', [.7,.4,.2,1]), 4, 'color')
            mass = config.get('mass', 0.)
            if not isinstance(mass, (int,float)) or not self.np.isfinite(mass) or mass < 0 or min(size) <= 0 or any(x<0 or x>1 for x in rgba):
                raise ValueError('Invalid size, mass or color')
            if spec.body(name):
                raise ValueError('Body already exists')
            body = spec.worldbody.add_body(name=name, pos=pos)
            if mass > 0:
                body.add_freejoint(name=name+'_free')
            body.add_geom(name=name+'_geom', type=self.mj.mjtGeom.mjGEOM_BOX,
                          size=[x/2 for x in size], rgba=rgba, **({'mass':mass} if mass > 0 else {}))
        elif operation in ('robot','asset'):
            if set(config)-{'name','path','position'} or not config.get('path'):
                raise ValueError('robot requires local MJCF path, name and optional position')
            from loop_robot.toolchain.composition import child_asset
            if (Path(config['path']).parent/'.loop-assets.json').exists():
                child = child_asset(config['path'], name)
            else:
                child = self.mj.MjSpec.from_file(str(Path(config['path']).resolve()))
                for item in list(child.worldbody.geoms)+list(child.worldbody.lights)+list(child.worldbody.cameras):
                    child.delete(item)
            frame = spec.worldbody.add_frame(pos=vector(config.get('position',[0,0,0]),3,'position'))
            spec.attach(child, prefix=name+'/', frame=frame)
        else:
            raise ValueError('Supported edits: box, robot')
        self._commit(spec)
        return self.inspect()

    def camera(self, config):
        value = camera_config(config)
        spec = self.spec.copy()
        if spec.camera(value['name']):
            raise ValueError('Camera already exists; choose a new name')
        parent = spec.worldbody if value['parent'] == 'world' else spec.body(value['parent'])
        if parent is None:
            raise ValueError('Unknown camera parent')
        # MuJoCo clipping planes are global, reject inconsistent per-camera requests.
        if self.cameras and any((c['near'],c['far']) != (value['near'],value['far']) for c in self.cameras.values()):
            raise ValueError('MuJoCo cameras share clipping planes; use existing near/far')
        parent.add_camera(name=value['name'], pos=value['position'], quat=value['quaternion'], fovy=value['fovy'])
        self._commit(spec)
        self.model.vis.map.znear = value['near']/self.model.stat.extent
        self.model.vis.map.zfar = value['far']/self.model.stat.extent
        self.cameras[value['name']] = value
        return value

    def reset(self, seed=0):
        if type(seed) is not int or seed < 0:
            raise ValueError('seed must be a nonnegative integer')
        if self.model.nkey:
            self.mj.mj_resetDataKeyframe(self.model, self.data, 0)
        else:
            self.mj.mj_resetData(self.model, self.data)
        self.mj.mj_forward(self.model, self.data)
        self.seed=seed
        return self.inspect()

    def step(self, action, steps=1):
        if type(steps) is not int or not 1 <= steps <= 1000:
            raise ValueError('steps must be 1..1000')
        action = vector(action, self.model.nu, 'actuator controls')
        for i, v in enumerate(action):
            if self.model.actuator_ctrllimited[i] and not self.model.actuator_ctrlrange[i,0] <= v <= self.model.actuator_ctrlrange[i,1]:
                raise ValueError('Action exceeds actuator limit')
        self.data.ctrl[:] = action
        warnings = self.data.warning.number.copy()
        self.mj.mj_step(self.model, self.data, nstep=steps)
        if not self.np.isfinite(self.data.qpos).all() or self.np.any(self.data.warning.number > warnings):
            raise RuntimeError('Physics instability; reset before retrying')
        return self.inspect()

    def inspect(self):
        m, d, mj = self.model, self.data, self.mj
        from loop_robot.toolchain.composition import geom_bounds
        bounds = {}
        for i in range(1,m.nbody):
            ids = [g for g in range(m.ngeom) if m.geom_bodyid[g] == i and m.geom_type[g] != mj.mjtGeom.mjGEOM_PLANE]
            if ids:
                pairs = [geom_bounds(m,d,g) for g in ids]
                bounds[mj.mj_id2name(m,mj.mjtObj.mjOBJ_BODY,i) or str(i)] = {
                    'min':self.np.min([p[0] for p in pairs],axis=0).tolist(), 'max':self.np.max([p[1] for p in pairs],axis=0).tolist()}
        digest = hashlib.sha256(self.spec.to_xml().encode())
        for name, content in sorted(self.spec.assets.items()):
            digest.update(name.encode()); digest.update(bytes(content))
        return {'backend':self.backend, 'version':mj.__version__, 'time':float(d.time), 'seed':self.seed,
                'scene_sha256':digest.hexdigest(), 'qpos':d.qpos.tolist(), 'qvel':d.qvel.tolist(),
                'action':d.ctrl.tolist(), 'action_space':{'kind':'actuator_control','names':[mj.mj_id2name(m,mj.mjtObj.mjOBJ_ACTUATOR,i) or str(i) for i in range(m.nu)],
                    'bounds':[m.actuator_ctrlrange[i].tolist() if m.actuator_ctrllimited[i] else None for i in range(m.nu)]},
                'bodies':{mj.mj_id2name(m,mj.mjtObj.mjOBJ_BODY,i) or str(i):d.xpos[i].tolist() for i in range(1,m.nbody)},
                'bounds':bounds, 'contacts':int(d.ncon), 'min_contact_distance': min([float(d.contact[i].dist) for i in range(d.ncon)], default=0.),
                'cameras':self.cameras, 'state_source':'physics', 'timeline':'paused'}

    def capture(self, names):
        if not isinstance(names,list) or not names or len(names)>8 or len(set(names)) != len(names):
            raise ValueError('Select 1..8 unique cameras')
        if any(name not in self.cameras for name in names):
            raise ValueError('Unknown camera')
        frames = {}
        for name in names:
            c = self.cameras[name]
            renderer = self.renderers.get(name)
            if renderer is None:
                renderer = self.mj.Renderer(self.model, height=c['height'], width=c['width'])
                self.renderers[name] = renderer
            renderer.disable_depth_rendering(); renderer.disable_segmentation_rendering()
            renderer.update_scene(self.data, camera=name)
            rgb = renderer.render().copy()
            renderer.enable_depth_rendering()
            depth = renderer.render().copy()
            renderer.disable_depth_rendering(); renderer.enable_segmentation_rendering()
            mask = renderer.render().copy()
            renderer.disable_segmentation_rendering()
            idx = self.mj.mj_name2id(self.model,self.mj.mjtObj.mjOBJ_CAMERA,name)
            frames[name] = {'rgb':rgb, 'depth':depth, 'segmentation':mask,
                'calibration':calibration(c,self.data.cam_xpos[idx],self.data.cam_xmat[idx].reshape(3,3)),
                'labels':{str(g):self.mj.mj_id2name(self.model,self.mj.mjtObj.mjOBJ_GEOM,g) or str(g) for g in range(self.model.ngeom)}}
        return frames

    def close_renderers(self):
        for renderer in self.renderers.values():
            renderer.close()
        self.renderers.clear()

    def close(self):
        self.close_renderers()
