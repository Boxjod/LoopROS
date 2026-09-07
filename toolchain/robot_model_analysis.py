"""Offline FK/Jacobian/dynamics from the exact verified scene snapshot."""
from toolchain.model_assets import snapshot


def analyze(scene, operation, body=None, qpos=None, qvel=None, qacc=None, world_wrench=None):
    import mujoco
    import numpy as np
    if operation not in ('kinematics','dynamics','wrench_to_joint'):
        raise ValueError('operation must be kinematics, dynamics or wrench_to_joint')
    content,assets,digest=snapshot(scene)
    model=mujoco.MjModel.from_xml_string(content.decode(),assets=assets)
    if model.nv>256: raise ValueError('Model analysis limited to 256 generalized velocities')
    data=mujoco.MjData(model)
    if model.nkey: mujoco.mj_resetDataKeyframe(model,data,0)
    def vector(value,n,name):
        if not isinstance(value,list) or len(value)!=n or any(type(x) not in (float,int) for x in value): raise ValueError(name+' requires '+str(n)+' numbers')
        result=np.asarray(value,dtype=float)
        if not np.isfinite(result).all(): raise ValueError(name+' must be finite')
        return result
    if qpos is not None: data.qpos[:]=vector(qpos,model.nq,'qpos')
    for i in range(model.njnt):
        typ=model.jnt_type[i];a=model.jnt_qposadr[i]
        if typ in (mujoco.mjtJoint.mjJNT_FREE,mujoco.mjtJoint.mjJNT_BALL):
            quat=data.qpos[a+3:a+7] if typ==mujoco.mjtJoint.mjJNT_FREE else data.qpos[a:a+4]
            if not np.isclose(np.linalg.norm(quat),1,atol=1e-6): raise ValueError('qpos contains a non-unit quaternion')
        elif model.jnt_limited[i] and not model.jnt_range[i,0]<=data.qpos[a]<=model.jnt_range[i,1]:
            raise ValueError('qpos violates joint limit: '+str(model.joint(i).name))
    if qvel is not None: data.qvel[:]=vector(qvel,model.nv,'qvel')
    acceleration=vector(qacc,model.nv,'qacc') if qacc is not None else np.zeros(model.nv)
    mujoco.mj_forward(model,data)
    if not np.isfinite(data.qacc).all(): raise ValueError('Non-finite model dynamics')
    result={'operation':operation,'scene_sha256':digest,'mujoco_version':mujoco.__version__,
            'state_source':'explicit qpos/qvel or saved home state; not live hardware telemetry',
            'qpos':data.qpos.tolist(),'qvel':data.qvel.tolist(),'nq':model.nq,'nv':model.nv,
            'dof_order':[{'index':i,'joint':model.joint(int(model.dof_jntid[i])).name,
                          'joint_type':int(model.jnt_type[model.dof_jntid[i]])} for i in range(model.nv)],
            'hardware_command_sent':False,'controls_viewer':False}
    if operation in ('kinematics','wrench_to_joint'):
        if not isinstance(body,str): raise ValueError('Specify an exact body name from simulator_status')
        bid=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_BODY,body)
        if bid<1: raise ValueError('Unknown body; use an exact body name from simulator_status')
        jp=np.zeros((3,model.nv));jr=np.zeros_like(jp);mujoco.mj_jacBody(model,data,jp,jr,bid)
        result.update(body=body,world_position_m=data.xpos[bid].tolist(),world_rotation=data.xmat[bid].reshape(3,3).tolist(),
                      jacobian_linear=jp.tolist(),jacobian_angular=jr.tolist(),jacobian_frame='world; reference point is body origin')
        if operation=='wrench_to_joint':
            wrench=vector(world_wrench,6,'world_wrench [Fx,Fy,Fz,Mx,My,Mz]')
            result.update(generalized_load=(jp.T@wrench[:3]+jr.T@wrench[3:]).tolist(),
                          formula='generalized_load = Jv.T * force_world + Jw.T * moment_world',
                          interpretation='External wrench at body origin. Compensation is its negative, plus modeled gravity/dynamic terms; not actuator commands.')
    else:
        mass=np.empty((model.nv,model.nv))
        if hasattr(data,"qM"):
            mujoco.mj_fullM(model,mass,data.qM)
        else:
            mujoco.mj_fullM(model,data,mass)
        bias=data.qfrc_bias.copy();passive=data.qfrc_passive.copy()
        data.qacc[:]=acceleration;mujoco.mj_inverse(model,data)
        result.update(mass_matrix=mass.tolist(),bias_force=bias.tolist(),passive_force=passive.tolist(),
                      requested_qacc=acceleration.tolist(),inverse_generalized_force=data.qfrc_inverse.tolist(),
                      contact_count=int(data.ncon),constraints_force=data.qfrc_constraint.tolist(),
                      convention='M(q)*qacc + bias = passive + actuator/applied + constraint; qfrc_inverse includes MuJoCo inverse constraint handling. Generalized force is not ctrl.',
                      force_units='Rotational DOFs: Nm; translational DOFs: N. No universal current or actuator mapping.')
    return result
