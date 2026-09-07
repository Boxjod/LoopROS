"""Node command surface shared by the terminal and Master tool broker."""
import json
import shlex

HELP = '''/node list                         List nodes and current focus
/node start sim_arm NAME            Start a persistent MuJoCo joint node
/node start serial_rx NAME PORT BAUD  Start an explicit serial receive node
/node start ros NAME CONFIG.json    Start ROS 2/1 sensor observer from a local JSON config
/node profiles                     Inspect user process profiles and hashes
/node inspect JSON                 Inspect local/SSH ports, PIDs and RAM
/node terminate JSON               Stop inspected identities with explicit signal mode
/node start process NAME PROFILE   Start a reviewed local/SSH program without model polling
/node export_map NAME OBSERVATION   Save the latest fresh map as a local JSON artifact
/node send NAME TEXT               Send a line to its terminal (never send credentials)
/node use NAME|master               Switch terminal focus; other nodes keep running
/node status [NAME]                 Inspect heartbeat, state and command results
/node move NAME Q1 Q2               Queue simulated joint target (radians)
/node logs [NAME]                   Recent lifecycle and command events
/node stop NAME                    Stop and reap a node
While focused: status, move Q1 Q2, send TEXT, logs, stop, master (no LLM/API required).
Nodes are owned by this terminal session and stop when it exits.'''


def schema(name, description, properties, required):
    return {'type': 'function', 'function': {'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties, 'required': required,
                           'additionalProperties': False}}}


NODE_TOOLS = [
    schema('process_inspect', 'Inspect Linux local/SSH TCP listening port owners, exact PID identities, process RSS and available host RAM. No signals, no robot commands. Omit selectors for top RSS processes. Ports are not proof of service or motor readiness.',
           {'host': {'type': 'string', 'description': 'local (default) or SSH alias/user@hostname'},
            'ports': {'type': 'array', 'items': {'type': 'integer'}, 'maxItems': 32},
            'pids': {'type': 'array', 'items': {'type': 'integer'}, 'maxItems': 32}}, []),
    schema('process_stop', 'Stop exact inspected Linux PID identities locally or over SSH and verify process exit plus requested TCP port release. Select the user-authorized signal mode: graceful=INT, terminate=TERM, kill=KILL, escalate=INT then TERM then KILL. Does not stop replacement PIDs or prove hardware disabled; no blanket port kill.',
           {'host': {'type': 'string'}, 'ports': {'type': 'array', 'items': {'type': 'integer'}, 'maxItems': 32},
            'targets': {'type': 'array', 'minItems': 1, 'maxItems': 32, 'items': {'type': 'object',
                'properties': {'pid': {'type': 'integer'}, 'start_ticks': {'type': 'integer'}, 'boot_id': {'type': 'string'}},
                'required': ['pid', 'start_ticks', 'boot_id'], 'additionalProperties': False}},
            'mode': {'type': 'string', 'enum': ['graceful', 'terminate', 'kill', 'escalate']},
            'wait_s': {'type': 'number', 'minimum': .1, 'maximum': 10}}, ['targets']),
    schema('node_profiles', 'List user process profiles, commands, working directories and content hashes. No execution; credentials must be supplied via named environment variables.', {}, []),
    schema('node_start', '启动常驻Loop Node；process运行用户配置的本地或SSH程序，无模型轮询；sim_arm为模拟，serial_rx仅接收；ros通过独立ROS解释器接收多模态摘要；starting不证明服务就绪',
           {'name': {'type': 'string'}, 'kind': {'type': 'string', 'enum': ['sim_arm', 'serial_rx', 'process', 'ros']},
            'config': {'type': 'object', 'description': 'ros accepts version (2 default or 1), absolute python, env, optional launch {argv,cwd} for a foreground ROS package, and topics [{name, topic, kind, max_age_s, required, qos}]; kinds: joints,force,imu,scan,image,points,odom,map,audio,tactile; qos: sensor,reliable,latched. Requires run_python=allow. process requires profile and expected_sha256 from node_profiles; runs user-owned code with run_python permission, not a hardware sandbox.'}}, ['name', 'kind']),
    schema('node_status', '查询节点进程、心跳、最新观测及命令结果；省略name列出全部',
           {'name': {'type': 'string'}}, []),
    schema('node_command', 'ros支持export_map {name:观测名}保存地图JSON；向process发送一行send text，或向sim_arm排队move；禁止输入凭据。queued不是成功，需检查node_status中的匹配command_id结果',
           {'name': {'type': 'string'}, 'action': {'type': 'string', 'enum': ['move', 'send', 'export_map']},
            'arguments': {'type': 'object', 'properties': {'name': {'type': 'string', 'description': 'ROS map observation name'}, 'target': {'type': 'array', 'items': {'type': 'number'}, 'minItems': 2, 'maxItems': 2}, 'text': {'type': 'string'}},
                          'additionalProperties': False}}, ['name', 'action', 'arguments']),
    schema('node_stop', '停止并回收指定Loop Node，不是硬件急停', {'name': {'type': 'string'}}, ['name']),
    schema('node_logs', '读取节点近期生命周期及命令日志', {'name': {'type': 'string'}}, ['name']),
]


def tool(app, name, args):
    if name in ('process_inspect', 'process_stop'):
        from loop_robot.terminal.process_control import run
        return run(app, name, args)
    with app.nodes.lock:
        return _tool(app, name, args)


def _tool(app, name, args):
    if name == 'node_profiles':
        if args:
            raise ValueError('node_profiles takes no arguments')
        from loop_robot.terminal.home import loop_home
        from loop_robot.toolchain.process_node import read_profile
        return {'profiles': [read_profile(p.stem) for p in sorted((loop_home() / 'processes').glob('*.json'))[:64]]}
    fields = {'node_start': ({'name', 'kind', 'config'}, {'name', 'kind'}),
              'node_status': ({'name'}, set()), 'node_command': ({'name', 'action', 'arguments'}, {'name', 'action', 'arguments'}),
              'node_stop': ({'name'}, {'name'}), 'node_logs': ({'name'}, {'name'})}
    allowed, required = fields[name]
    if not isinstance(args, dict) or set(args) - allowed or not required.issubset(args):
        raise ValueError('Invalid node tool arguments')
    if name in ('node_start', 'node_command'):
        app.permissions.check(name, args)
    if name == 'node_start':
        if args['kind'] in ('process', 'ros') and app.permissions.snapshot()['rules']['run_python'] != 'allow':
            raise PermissionError('Persistent process nodes require run_python=allow; inspect the profile before enabling host code execution')
        if args['kind'] == 'serial_rx':
            config = args.get('config', {})
            from loop_robot.toolchain.node_workers import serial_config
            config = serial_config(config)
            for dependency in ('open_serial', 'read_serial'):
                if app.permissions.snapshot()['rules'][dependency] != 'allow':
                    raise PermissionError('serial_rx requires an allow rule for ' + dependency + '; a one-shot serial approval cannot authorize a persistent node')
        if args['kind'] == 'sim_arm' and app.permissions.snapshot()['rules']['move_sim'] == 'deny':
            raise PermissionError('Simulation is stopped or move_sim is denied')
        return app.nodes.start(**args)
    if name == 'node_command':
        state = app.nodes.status(args['name'])
        if state['kind'] == 'ros':
            if app.permissions.snapshot()['rules']['run_python'] != 'allow':
                raise PermissionError('ROS map export requires run_python=allow')
            if args['action'] != 'export_map' or not isinstance(args['arguments'], dict) or set(args['arguments']) != {'name'}:
                raise ValueError('ROS accepts export_map with an observation name')
            return app.nodes.command(**args)
        if state['kind'] == 'process':
            if app.permissions.snapshot()['rules']['run_python'] != 'allow':
                raise PermissionError('Process terminal input requires run_python=allow')
            if args['action'] != 'send' or not isinstance(args['arguments'], dict) or set(args['arguments']) != {'text'}:
                raise ValueError('process accepts send with text')
            text = args['arguments']['text']
            if not isinstance(text, str) or len(text) > 2000:
                raise ValueError('process text must contain at most 2000 characters')
            return app.nodes.command(**args)
        if state['kind'] != 'sim_arm' or args['action'] != 'move' or not isinstance(args['arguments'], dict) or set(args['arguments']) != {'target'}:
            raise ValueError('Only sim_arm move target=[q1,q2] is implemented')
        from loop_robot.toolchain.trajectory import validate_target
        validate_target(args['arguments']['target'], ((-1, 1), (-1, 1)))
        if app.permissions.snapshot()['rules']['move_sim'] != 'allow':
            raise PermissionError('Node move requires an allow rule for move_sim; use node_command rules for per-command approval')
        return app.nodes.command(**args)
    if name == 'node_status':
        return app.nodes.status(**args)
    if name == 'node_logs':
        state = app.nodes.status(args['name'])
        if state['kind'] == 'process':
            return {'output_tail': state['snapshot'].get('output_tail', ''), 'snapshot': state['snapshot'],
                    'events': app.nodes.logs(**args), 'output_log': state['output_log']}
        return app.nodes.logs(**args)
    return app.nodes.stop(**args)


def dispatch(app, tail):
    parts = shlex.split(tail)
    if not parts or parts == ['list']:
        return json.dumps({'focus': app.node_focus, **app.tool('node_status', {})}, ensure_ascii=False)
    if parts == ['help']:
        return HELP
    verb, *args = parts
    if verb in ('inspect', 'terminate'):
        payload = tail.strip().partition(' ')[2]
        return json.dumps(app.tool('process_inspect' if verb == 'inspect' else 'process_stop', json.loads(payload)), ensure_ascii=False)
    if verb == 'profiles' and not args:
        return json.dumps(app.tool('node_profiles', {}), ensure_ascii=False)
    if verb == 'start' and len(args) == 3 and args[0] == 'ros':
        from pathlib import Path
        path = Path(args[2]).expanduser()
        if path.stat().st_size > 64000:
            raise ValueError('ROS config exceeds 64 KB')
        config = json.loads(path.read_text(encoding='utf-8'))
        return json.dumps(app.tool('node_start', {'kind': 'ros', 'name': args[1], 'config': config}), ensure_ascii=False)
    if verb == 'start' and len(args) == 3 and args[0] == 'process':
        from loop_robot.toolchain.process_node import read_profile
        profile = read_profile(args[2])
        return json.dumps(app.tool('node_start', {'kind': 'process', 'name': args[1],
                          'config': {'profile': args[2], 'expected_sha256': profile['sha256']}}), ensure_ascii=False)
    if verb == 'export_map' and len(args) == 2:
        return json.dumps(app.tool('node_command', {'name': args[0], 'action': 'export_map', 'arguments': {'name': args[1]}}), ensure_ascii=False)
    if verb == 'send' and len(args) >= 2:
        return json.dumps(app.tool('node_command', {'name': args[0], 'action': 'send', 'arguments': {'text': ' '.join(args[1:])}}), ensure_ascii=False)
    if verb == 'use' and len(args) == 1:
        if args[0] != 'master':
            state = app.nodes.status(args[0])
            if not state['process_alive']:
                raise ValueError('Cannot focus a stopped node')
        app.node_focus = args[0]
        return 'Terminal focus: ' + args[0] + '. Background nodes keep running.'
    if verb == 'start' and len(args) in (2, 4):
        kind, name = args[:2]
        config = {} if len(args) == 2 else {'port': args[2], 'baud': int(args[3])}
        return json.dumps(app.tool('node_start', {'name': name, 'kind': kind, 'config': config}), ensure_ascii=False)
    if verb in ('status', 'logs') and len(args) <= 1:
        name = args[0] if args else app.node_focus
        if name == 'master':
            return json.dumps(app.tool('node_status', {}), ensure_ascii=False)
        return json.dumps(app.tool('node_' + verb, {'name': name}), ensure_ascii=False)
    if verb == 'stop' and len(args) == 1:
        return json.dumps(app.tool('node_stop', {'name': args[0]}), ensure_ascii=False)
    if verb == 'move' and len(args) == 3:
        return json.dumps(app.tool('node_command', {'name': args[0], 'action': 'move',
                          'arguments': {'target': [float(x) for x in args[1:]]}}), ensure_ascii=False)
    raise ValueError(HELP)


def focused_reply(app, text, attachments=None):
    if attachments:
        raise ValueError('Node console accepts commands only; switch to /node use master for media')
    parts = shlex.split(text)
    if parts in (['master'], ['back']):
        return dispatch(app, 'use master')
    if parts == ['help']:
        return HELP
    if parts in (['status'], ['状态'], ['logs'], ['stop'], ['停止']):
        verb = {'状态': 'status', '停止': 'stop'}.get(parts[0], parts[0])
        return dispatch(app, verb + ' ' + app.node_focus)
    if len(parts) == 3 and parts[0] == 'move':
        return dispatch(app, 'move ' + app.node_focus + ' ' + ' '.join(parts[1:]))
    if parts and parts[0] == 'send':
        return dispatch(app, 'send ' + app.node_focus + ' ' + shlex.join(parts[1:]))
    raise ValueError('Node ' + app.node_focus + ' accepts: status, move Q1 Q2, send TEXT, logs, stop, master. Use /node use master for conversation.')
