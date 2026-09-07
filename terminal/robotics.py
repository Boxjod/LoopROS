"""Robotics tools: explicit evidence, official references and offline calculations."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import time
import uuid
from urllib.parse import urlsplit

from loop_robot.terminal.web import dispatch as web_dispatch, request, clean_html

SOURCES={
 'ros2':('https://docs.ros.org/en/{version}/','ROS 2 nodes/topics/services/actions, QoS, tf2, rosbag2; match ROS_DISTRO'),
 'ros2_control':('https://control.ros.org/{version}/','Hardware interfaces, controller manager, joint limits, update loop, PID'),
 'moveit':('https://moveit.picknik.ai/{version}/','MoveIt planning, kinematics plugins, collision checking and execution'),
 'pinocchio':('https://docs.ros.org/en/{version}/p/pinocchio/','Rigid-body FK/Jacobian, RNEA, CRBA, ABA; match installed package'),
 'mujoco':('https://mujoco.readthedocs.io/en/{version}/','Simulation, model state, contacts, Jacobians and dynamics'),
 'mink':('https://kevinzakka.github.io/mink/','Constrained differential IK; posture, task weights and velocity limits'),
 'dynamixel':('https://emanual.robotis.com/docs/en/dxl/','ROBOTIS model-specific control tables, Protocol 1/2, units and error bits'),
 'odrive':('https://docs.odriverobotics.com/v/{version}/','Motor parameters, FOC current/torque, encoder, firmware-specific faults'),
 'socketcan':('https://docs.kernel.org/networking/can.html','CAN interfaces, errors, bus-off and SocketCAN semantics'),
 'ethercat':('https://infosys.beckhoff.com/','EtherCAT master/slave states, distributed clocks; identify exact device/ESI'),
 'simplefoc':('https://docs.simplefoc.com/','FOC current sensing, motor/sensor alignment and nested control loops'),
}


def source_url(source,version=None):
    if source not in SOURCES: raise ValueError('Unknown source; use robot_toolchains for the registry')
    defaults={'ros2':os.environ.get('ROS_DISTRO','rolling'),'ros2_control':os.environ.get('ROS_DISTRO','rolling'),
              'pinocchio':os.environ.get('ROS_DISTRO','rolling'),'moveit':'main','mujoco':'stable','odrive':'latest'}
    selected=version or defaults.get(source,'unversioned')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,40}',selected): raise ValueError('Invalid documentation version')
    return SOURCES[source][0].format(version=selected),selected


def docs(directory,source,query='',version=None):
    base,version=source_url(source,version)
    if not isinstance(query,str) or len(query)>300: raise ValueError('query must contain at most 300 characters')
    allowed=urlsplit(base);url=base;search_error=None
    if query:
        try:
            found=web_dispatch('web_search',{'query':'site:'+allowed.netloc+allowed.path+' '+query,'limit':5})
            for entry in found.get('results',[]):
                candidate=entry.get('url','');parts=urlsplit(candidate)
                if parts.scheme=='https' and parts.netloc==allowed.netloc and parts.path.startswith(allowed.path): url=candidate;break
        except Exception as exc: search_error=str(exc)[:200]
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    cached=json.loads(path.read_text()) if path.exists() else None
    if cached and time.time()-cached['fetched_epoch']<86400:
        page=cached
    else:
        try:
            raw=request(url)
            actual=urlsplit(raw['url'])
            if actual.scheme!='https' or actual.netloc!=allowed.netloc or not actual.path.startswith(allowed.path):
                raise ValueError('Documentation redirected outside the official version namespace')
            title,text=clean_html(raw['body'])
            page={'source':source,'version_namespace':version,'url':raw['url'],'title':title,'text':text,
                  'retrieved_at':raw['retrieved_at'],'fetched_epoch':time.time()}
            path.write_text(json.dumps(page,ensure_ascii=False))
        except Exception as exc:
            if not cached: raise
            page={**cached,'stale':True,'refresh_error':str(exc)[:300]}
    text=page['text'];start=0
    for word in re.findall(r'[A-Za-z][A-Za-z0-9_]{3,}',query):
        index=text.lower().find(word.lower())
        if index>=0: start=max(0,index-400);break
    return {**{k:v for k,v in page.items() if k!='fetched_epoch'},'text':text[start:start+10000],
            'truncated':len(text)>10000,'search_error':search_error,
            'version_note':'Documentation namespace is not proof of installed hardware firmware compatibility; match model, firmware and signal units.'}


def inventory():
    packages={}
    for name in ('mujoco','mink','numpy','scipy','pin','pinocchio','python-can','pyserial','pysoem','dynamixel-sdk','odrive'):
        try: packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name]=None
    return {'python_packages':packages,'executables':{name:shutil.which(name) for name in ('ros2','colcon','rviz2','gz','candump','cansend','ip','ethercat')},
            'ROS_DISTRO':os.environ.get('ROS_DISTRO'),
            'documentation':{name:{'url':source_url(name)[0],'purpose':value[1]} for name,value in SOURCES.items()},
            'motor_sdk_sources': {
                'dynamixel-sdk': {'url':'https://emanual.robotis.com/docs/en/software/dynamixel/dynamixel_sdk/overview/',
                                 'requires':'Exact actuator model, protocol version, transport, ID and control table'},
                'odrive': {'url':'https://docs.odriverobotics.com/v/latest/guides/odrivetool-setup.html',
                          'requires':'ODrive hardware generation and firmware, axis and calibrated motor/encoder configuration'}},
            'integration':{'serial':'existing receive-only adapter','motor_write_drivers':'feetech_sts3215_host_primitive; not exposed to terminal',
                           'mujoco':'verified scene and simulator tools','mink':'existing offline FK/differential IK adapter',
                           'ros2':'read-only adapter exists; package/executable presence alone is not integration verification',
                           'CAN_EtherCAT':'documentation/inventory; no hardware transmit tools'},
            'scope':'Current Python environment and PATH only; no imports of device SDKs or connection attempts'}


FAULTS=[
 ('permission',r'permission denied|operation not permitted|权限不足|权限拒绝', 'host_access',
  ['端口/网络接口权限、设备占用或容器映射可能阻止访问'],['核对实际设备路径、属组、应用运行身份和占用进程；不要用放宽全部设备权限代替定位']),
 ('missing_device',r'no such file|device not found|找不到设备|设备不存在','enumeration',
  ['设备断开、路径变化或驱动未绑定'],['重新枚举并按USB身份/by-id核对；比较拔插时间的内核日志与接口状态']),
 ('timeout',r'timeout|timed out|超时|no response','transport_protocol',
  ['供电/线缆、波特率、节点ID、协议版本或半双工方向均可能导致无响应'],['先确认型号和固件对应的电气接口、供电、波特率、ID与协议；抓取带时间戳的收发字节，不能凭超时确认电机损坏']),
 ('bus_off',r'bus[-_ ]?off','CAN_link',
  ['CAN错误计数过高；位率、接线、终端或无ACK等需要排查'],['读取接口状态、错误计数及bus-off时间；核对所有节点位率、终端和接线。复位bus-off不能代替根因排查']),
 ('overcurrent',r'over.?current|过流|current limit','power_or_control',
  ['堵转/负载、接线、相电阻或电流环参数需要区分'],['记录故障前电流、母线电压、速度/位置和设定值；核对厂商电流定义与额定/峰值限制，不直接提高限流']),
 ('encoder',r'encoder|编码器|position sensor','feedback',
  ['编码器供电/接线、CPR定义、方向、索引或标定状态可能不匹配'],['核对编码器类型及CPR/PPR/四倍频定义、原始计数、角度单位、方向和时间戳；不能从一个错误码推断需要重标定']),
 ('voltage',r'over.?voltage|under.?voltage|过压|欠压','power',
  ['供电压降或制动回馈可能导致电压越限'],['对比母线电压记录和厂商阈值；区分加速欠压与减速回馈过压，核对制动和电源吸收能力']),
 ('oscillation',r'oscillat|振荡|抖动|overshoot|超调','closed_loop',
  ['反馈符号/单位、采样延迟、饱和积分、机械柔性和增益都需核对'],['先比对目标/反馈/输出与时间戳、饱和标记；确认负反馈和单位后做离线PID试验，不直接上真机增大增益']),
]


def diagnose(observation,model=None,firmware=None,transport=None,error_code=None):
    if not isinstance(observation,str) or not 1<=len(observation)<=16000: raise ValueError('Provide 1..16000 characters of actual observations/logs')
    facts={'observation':observation,'model':model,'firmware':firmware,'transport':transport,'error_code':error_code}
    findings=[{'category':name,'layer':layer,'hypotheses':hypotheses,'next_checks':checks}
              for name,pattern,layer,hypotheses,checks in FAULTS if re.search(pattern,observation,re.I)]
    missing=[key for key in ('model','firmware','transport') if not facts[key]]
    return {'evidence_origin':'user-provided observation; not an independently verified device reading','facts':facts,
            'missing_context':missing,'findings':findings,'verdict':'inconclusive',
            'next_step':'查对应型号/固件官方手册并补采证据后缩小原因；现有devices/serial_status/read_serial工具可按原权限使用。',
            'error_code_decoded':False,'note':'Error code meanings are model/firmware-specific; no guessed register writes, fault clearing, calibration or motor enable.',
            'hardware_command_sent':False}


def record(app,operation,args,result):
    from loop_robot.core.store import EventStore
    from loop_robot.core.contracts import Episode,Review,record as serialize
    directory=app.state_dir/'engineering';directory.mkdir(parents=True,exist_ok=True)
    path=directory/(uuid.uuid4().hex+'.json')
    path.write_text(json.dumps({'operation':operation,'inputs':args,'result':result},ensure_ascii=False,indent=2,allow_nan=False))
    with EventStore(directory/'evidence.sqlite') as store:
        episode=Episode(uuid.uuid4().hex,1,'robot-engineering','offline',actions=[{'tool':operation,'arguments':args}],observations=[{'report':str(path)}])
        verdict='inconclusive' if result.get('verdict')=='inconclusive' else 'pass'
        review=Review(verdict,1. if verdict=='pass' else 0.,'Computation/observation report saved; no hardware execution or physical task success established')
        store.append_episode_review(episode,review)
    if 'samples' in result:
        rows=result['samples'];result={k:v for k,v in result.items() if k!='samples'}
        result['sample_count']=len(rows);result['samples_preview']=rows[::max(1,len(rows)//30)]
    if len(result.get('mass_matrix',[]))>16:
        matrix=result['mass_matrix'];result={k:v for k,v in result.items() if k!='mass_matrix'}
        result['mass_matrix_summary']={'shape':[len(matrix),len(matrix)],'diagonal':[row[i] for i,row in enumerate(matrix)],'full_matrix_in_report':True}
    return {**result,'report':str(path),'review':serialize(review)}


def dispatch(app,name,args):
    from loop_robot.terminal.feetech import NAMES, dispatch as feetech_dispatch
    if name in NAMES: return feetech_dispatch(app, name, args)
    if name=='robot_toolchains':
        if args!={}: raise ValueError('robot_toolchains takes no arguments')
        return inventory()
    if name=='robot_docs':
        if args.get('query'): app.permissions.check('web_search',{'query':args['query']})
        return docs(app.state_dir/'robot_docs_cache',**args)
    if name=='robot_diagnose': return record(app,name,args,diagnose(**args))
    if name=='motor_torque':
        from loop_robot.toolchain.robot_engineering import current_to_torque
        return record(app,name,args,current_to_torque(args))
    if name=='pid_trial':
        from loop_robot.toolchain.robot_engineering import pid_trial
        return record(app,name,args,pid_trial(args))
    if name=='robot_model_analysis':
        if app.latest_scene is None: raise ValueError('No verified scene selected; load a robot model first')
        from loop_robot.toolchain.robot_model_analysis import analyze
        return record(app,name,args,analyze(app.latest_scene,**args))
    raise ValueError('Unknown robotics tool')


def schema(name,description,properties,required=()):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':list(required),'additionalProperties':False}}}
NUM={'type':'number'};TEXT={'type':'string'};VEC={'type':'array','items':NUM}
ROBOT_TOOLS=[
 schema('robot_toolchains','只读检查当前环境机器人库/命令及官方文档入口；不安装、连接设备或发送数据。',{}),
 schema('robot_docs','检索机器人官方手册；按ROS发行版/驱动固件查PID、运动学、动力学、电机控制/故障。未知厂商可用web_search查其官方文档，不能猜寄存器。',{'source':{'type':'string','enum':list(SOURCES)},'query':TEXT,'version':TEXT},('source',)),
 schema('robot_diagnose','根据实际日志分层排查端口、CAN、编码器、供电、电流或控制振荡，区分观测/假设/缺失信息；不清故障/标定/使能真机。',{'observation':TEXT,'model':TEXT,'firmware':TEXT,'transport':TEXT,'error_code':TEXT},('observation',)),
 schema('motor_torque','带单位校验的电流→电机轴/减速器输出轴力矩估算。必须知道电流和Kt的对应定义；母线电流/负载百分比不能直接换算，不发送控制命令。',
        {'current_A':NUM,'kt_Nm_per_A':NUM,'current_basis':{'type':'string','enum':['dc_armature','iq_peak','iq_rms','phase_peak','phase_rms']},'kt_current_basis':TEXT,'current_offset_A':NUM,'gear_ratio':NUM,'efficiency':NUM},('current_A','kt_Nm_per_A','current_basis','kt_current_basis')),
 schema('pid_trial','实际运行离线单轴PID试验（单位Nm/rad、抗积分饱和、测量微分低通），输出误差/超调/饱和比例和轨迹报告；不自动下发增益到电机。',
        {key:NUM for key in ('kp','ki','kd','inertia_kg_m2','damping_Nm_s_per_rad','torque_limit_Nm','target_rad','dt_s','duration_s','initial_rad','derivative_filter_s','load_torque_Nm')},('kp','ki','kd','inertia_kg_m2','damping_Nm_s_per_rad','torque_limit_Nm','target_rad')),
 schema('robot_model_analysis','根据当前校验机器人模型离线计算FK、世界坐标雅可比、惯量矩阵、逆动力学或J转置力映射。默认home状态；不改变窗口/硬件。关节广义力不等于actuator ctrl。',
        {'operation':{'type':'string','enum':['kinematics','dynamics','wrench_to_joint']},'body':TEXT,'qpos':VEC,'qvel':VEC,'qacc':VEC,'world_wrench':VEC},('operation',)),
]
from loop_robot.terminal.feetech import TOOLS as FEETECH_TOOLS
ROBOT_TOOLS += FEETECH_TOOLS
ROBOT_NAMES={t['function']['name'] for t in ROBOT_TOOLS}
