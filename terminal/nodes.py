"""Node command surface shared by the terminal and Master tool broker."""
import json
import shlex

HELP = '''/node list                         List nodes and current focus
/node start sim_arm NAME            Start a persistent MuJoCo joint node
/node start serial_rx NAME PORT BAUD  Start an explicit serial receive node
/node use NAME|master               Switch terminal focus; other nodes keep running
/node status [NAME]                 Inspect heartbeat, state and command results
/node move NAME Q1 Q2               Queue simulated joint target (radians)
/node logs [NAME]                   Recent lifecycle and command events
/node stop NAME                    Stop and reap a node
While focused: status, move Q1 Q2, logs, stop, master (no LLM/API required).
Nodes are owned by this terminal session and stop when it exits.'''


def schema(name, description, properties, required):
    return {'type': 'function', 'function': {'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties, 'required': required,
                           'additionalProperties': False}}}


NODE_TOOLS = [
    schema('node_start', '启动常驻Loop Node；sim_arm为MuJoCo模拟，serial_rx仅接收；返回starting不证明就绪',
           {'name': {'type': 'string'}, 'kind': {'type': 'string', 'enum': ['sim_arm', 'serial_rx']},
            'config': {'type': 'object'}}, ['name', 'kind']),
    schema('node_status', '查询节点进程、心跳、最新观测及命令结果；省略name列出全部',
           {'name': {'type': 'string'}}, []),
    schema('node_command', '向sim_arm排队move指令；queued不是成功，需检查node_status中的匹配command_id结果',
           {'name': {'type': 'string'}, 'action': {'type': 'string', 'enum': ['move']},
            'arguments': {'type': 'object', 'properties': {'target': {'type': 'array', 'items': {'type': 'number'}, 'minItems': 2, 'maxItems': 2}},
                          'required': ['target'], 'additionalProperties': False}}, ['name', 'action', 'arguments']),
    schema('node_stop', '停止并回收指定Loop Node，不是硬件急停', {'name': {'type': 'string'}}, ['name']),
    schema('node_logs', '读取节点近期生命周期及命令日志', {'name': {'type': 'string'}}, ['name']),
]


def tool(app, name, args):
    with app.nodes.lock:
        return _tool(app, name, args)


def _tool(app, name, args):
    fields = {'node_start': ({'name', 'kind', 'config'}, {'name', 'kind'}),
              'node_status': ({'name'}, set()), 'node_command': ({'name', 'action', 'arguments'}, {'name', 'action', 'arguments'}),
              'node_stop': ({'name'}, {'name'}), 'node_logs': ({'name'}, {'name'})}
    allowed, required = fields[name]
    if not isinstance(args, dict) or set(args) - allowed or not required.issubset(args):
        raise ValueError('Invalid node tool arguments')
    if name in ('node_start', 'node_command'):
        app.permissions.check(name, args)
    if name == 'node_start':
        if args['kind'] == 'serial_rx':
            config = args.get('config', {})
            from toolchain.node_workers import serial_config
            config = serial_config(config)
            for dependency in ('open_serial', 'read_serial'):
                if app.permissions.snapshot()['rules'][dependency] != 'allow':
                    raise PermissionError('serial_rx requires an allow rule for ' + dependency + '; a one-shot serial approval cannot authorize a persistent node')
        if args['kind'] == 'sim_arm' and app.permissions.snapshot()['rules']['move_sim'] == 'deny':
            raise PermissionError('Simulation is stopped or move_sim is denied')
        return app.nodes.start(**args)
    if name == 'node_command':
        state = app.nodes.status(args['name'])
        if state['kind'] != 'sim_arm' or args['action'] != 'move' or not isinstance(args['arguments'], dict) or set(args['arguments']) != {'target'}:
            raise ValueError('Only sim_arm move target=[q1,q2] is implemented')
        from toolchain.trajectory import validate_target
        validate_target(args['arguments']['target'], ((-1, 1), (-1, 1)))
        if app.permissions.snapshot()['rules']['move_sim'] != 'allow':
            raise PermissionError('Node move requires an allow rule for move_sim; use node_command rules for per-command approval')
        return app.nodes.command(**args)
    if name == 'node_status':
        return app.nodes.status(**args)
    if name == 'node_logs':
        return app.nodes.logs(**args)
    return app.nodes.stop(**args)


def dispatch(app, tail):
    parts = shlex.split(tail)
    if not parts or parts == ['list']:
        return json.dumps({'focus': app.node_focus, **app.tool('node_status', {})}, ensure_ascii=False)
    if parts == ['help']:
        return HELP
    verb, *args = parts
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
    raise ValueError('Node ' + app.node_focus + ' accepts: status, move Q1 Q2, logs, stop, master. Use /node use master for conversation.')
