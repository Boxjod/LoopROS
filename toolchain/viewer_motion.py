"""Bounded position-actuator trajectories for the currently loaded MuJoCo model."""
import math
import numpy as np


class Motion:
    def __init__(self, mj, model, data):
        self.mj,self.model,self.data=mj,model,data
        self.active=None
        self.result={'state':'idle'}

    def mapping(self, robot):
        m=self.model;mj=self.mj
        pairs=[]
        for a in range(m.nu):
            name=mj.mj_id2name(m,mj.mjtObj.mjOBJ_ACTUATOR,a) or ''
            if not name.startswith(robot+'/') or int(m.actuator_trntype[a])!=int(mj.mjtTrn.mjTRN_JOINT):continue
            j=int(m.actuator_trnid[a,0])
            if int(m.jnt_type[j])!=int(mj.mjtJoint.mjJNT_HINGE):continue
            gain=m.actuator_gainprm[a,0]
            if not m.actuator_ctrllimited[a] or gain<=0 or not np.isclose(m.actuator_biasprm[a,1],-gain) or not np.isclose(m.actuator_gear[a,0],1):
                raise ValueError('Trajectory requires bounded position actuators with unit gear')
            pairs.append((a,j,int(m.jnt_qposadr[j]),int(m.jnt_dofadr[j])))
        if not pairs:raise ValueError('No supported position-actuated arm named '+robot)
        return pairs

    def ik(self,pairs,body,position,start):
        mj,m=self.mj,self.model
        d=mj.MjData(m);d.qpos[:]=self.data.qpos;d.qpos[[p[2] for p in pairs]]=start
        target=np.array(position,dtype=float);dofs=[p[3] for p in pairs];qids=[p[2] for p in pairs]
        for _ in range(300):
            mj.mj_forward(m,d);error=target-d.xpos[body]
            if np.linalg.norm(error)<.008:return d.qpos[qids].copy()
            jac=np.zeros((3,m.nv));mj.mj_jacBody(m,d,jac,None,body);j=jac[:,dofs]
            delta=j.T@np.linalg.solve(j@j.T+np.eye(3)*.002,error)
            d.qpos[qids]+=np.clip(delta,-.06,.06)
            for a,jid,q,v in pairs:
                lo,hi=m.actuator_ctrlrange[a]
                if m.jnt_limited[jid]:lo=max(lo,m.jnt_range[jid,0]);hi=min(hi,m.jnt_range[jid,1])
                d.qpos[q]=np.clip(d.qpos[q],lo,hi)
        raise ValueError('Target unreachable with current base/support placement; IK residual %.3f m'%np.linalg.norm(error))

    def start(self,command):
        if self.active:raise ValueError('Motion already running; pause/stop it before replanning')
        robot=command['robot'];pairs=self.mapping(robot);m=self.model
        q=np.array([self.data.qpos[p[2]] for p in pairs]);duration=float(command['duration'])
        body=self.mj.mj_name2id(m,self.mj.mjtObj.mjOBJ_BODY,command.get('body',robot+'/hand'))
        if command['action']=='move_joints':goal=np.array(command['target'],dtype=float)
        else:
            if body<0:raise ValueError('Unknown end effector body')
            goal=self.ik(pairs,body,command['position'],q)
        if goal.shape!=q.shape:raise ValueError('Expected %d arm joint targets'%len(q))
        for value,(a,j,_,_) in zip(goal,pairs):
            lo,hi=m.actuator_ctrlrange[a]
            if m.jnt_limited[j]:lo=max(lo,m.jnt_range[j,0]);hi=min(hi,m.jnt_range[j,1])
            if not lo<=value<=hi:raise ValueError('Joint target outside limits')
        # Smoothstep peak velocity 1.5 * delta / duration; lengthen automatically.
        duration=max(duration,float(np.max(np.abs(goal-q)))*1.5/.5)
        if duration>30:raise ValueError('Trajectory exceeds 30 second bound')
        # Reject newly introduced robot/environment penetration along the path.
        d=self.mj.MjData(m);d.qpos[:]=self.data.qpos
        robot_bodies={i for i in range(1,m.nbody) if (self.mj.mj_id2name(m,self.mj.mjtObj.mjOBJ_BODY,i) or '').startswith(robot+'/')}
        baseline=set()
        for step in range(41):
            d.qpos[[p[2] for p in pairs]]=q+(goal-q)*step/40
            self.mj.mj_forward(m,d)
            for c in d.contact:
                pair=tuple(sorted((int(c.geom1),int(c.geom2))))
                bodies={int(m.geom_bodyid[c.geom1]),int(m.geom_bodyid[c.geom2])}
                if not bodies.intersection(robot_bodies) or c.dist>=-.002:continue
                if step==0:baseline.add(pair)
                elif pair not in baseline:raise ValueError('Planned path intersects scene geometry; no motion executed')
        self.active={'pairs':pairs,'start':q,'goal':goal,'time':float(self.data.time),'duration':duration,'body':body,'position':command.get('position')}
        self.result={'state':'running','robot':robot,'duration':duration,'target':goal.tolist(),'max_joint_error':float(np.max(np.abs(goal-q)))}
        return dict(self.result)

    def stop(self,reason='Stopped by operator'):
        if self.active:
            for a,j,q,v in self.active['pairs']:self.data.ctrl[a]=self.data.qpos[q]
            self.active=None;self.result={**self.result,'state':'cancelled','reason':reason}

    def tick(self):
        if not self.active:return
        t=self.active;elapsed=float(self.data.time)-t['time'];u=min(1,max(0,elapsed/t['duration']));blend=u*u*(3-2*u)
        for value,(a,j,q,v) in zip(t['start']+(t['goal']-t['start'])*blend,t['pairs']):self.data.ctrl[a]=value
        error=float(np.max(np.abs(t['goal']-np.array([self.data.qpos[p[2]] for p in t['pairs']]))))
        self.result['max_joint_error']=error
        if not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all():
            self.stop('Nonfinite simulation state');self.result['state']='failed';return
        if elapsed>=t['duration']:
            position_error=float(np.linalg.norm(self.data.xpos[t['body']]-t['position'])) if t['position'] is not None else None
            self.result['position_error']=position_error
            if error<.04 and (position_error is None or position_error<.02):
                self.active=None;self.result['state']='succeeded'
            elif elapsed>t['duration']+3:
                self.stop('Tracking tolerance not reached');self.result['state']='failed'


def repair_invalid_home(mj, model, data):
    """Repair zero-keyframe Panda poses outside declared limits; keep valid homes."""
    names=[mj.mj_id2name(model,mj.mjtObj.mjOBJ_JOINT,i) or '' for i in range(model.njnt)]
    for name in names:
        if not name.endswith('joint4'):continue
        prefix=name[:-len('joint4')]
        joints=[mj.mj_name2id(model,mj.mjtObj.mjOBJ_JOINT,prefix+'joint'+str(i)) for i in range(1,8)]
        if any(i<0 for i in joints):continue
        # Recognize Panda's asymmetric elbow limit, not an arbitrary seven-DOF arm.
        elbow=joints[3]
        if not np.allclose(model.jnt_range[elbow],[-3.0718,-.0698],atol=.001):continue
        value=data.qpos[model.jnt_qposadr[elbow]]
        if model.jnt_range[elbow,0]<=value<=model.jnt_range[elbow,1]:continue
        for j,value in zip(joints,[0,0,0,-1.5708,0,1.5708,-.7854]):
            data.qpos[model.jnt_qposadr[j]]=value
            for a in range(model.nu):
                if int(model.actuator_trntype[a])==int(mj.mjtTrn.mjTRN_JOINT) and model.actuator_trnid[a,0]==j:
                    data.ctrl[a]=value
    mj.mj_forward(model,data)
