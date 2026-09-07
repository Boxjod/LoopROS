"""Session configuration management; writes share the operator approval gate."""
import json
from pathlib import Path
import tempfile

from terminal.files import schema
from terminal.config import ROOT, user_config_file, validate_provider
from terminal.home import loop_home
from terminal.coding import atomic_text

TARGETS = ['permissions', 'profiles', 'config', 'agents', 'task_runtime', 'deployment']
TOOLS = [
    schema('settings_read', 'Inspect Loop configuration and supported settings. No credentials. Harness and Skills use harness_read/skill_read; keys use hidden /key input.',
           {'target': {'type': 'string', 'enum': TARGETS}}, []),
    schema('settings_update', 'Change Loop configuration on explicit user request. Default requires /approve of exact arguments; never approve yourself. Operations: permissions {mode} or {profile} or {action,rule}; profiles {operation:save|use|remove,name,config?,replace?}; config/agents/task_runtime replace full JSON document; deployment {manifest,host_id}. Read first. No API keys. Does not start devices or services. real/hardware selects real mode but does not install hardware drivers.',
           {'target': {'type': 'string', 'enum': TARGETS}, 'value': {'type': 'object'}}, ['target', 'value']),
]
NAMES = {t['function']['name'] for t in TOOLS}


def paths(app):
    from terminal.task_service import policy_path
    return {'config': loop_home() / 'config.json', 'agents': user_config_file('agents.json'),
            'task_runtime': policy_path(app.state_dir), 'deployment': app.state_dir / 'deployment.json'}


def no_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {'api_key', 'key', 'password', 'secret', 'token', 'authorization'}:
                raise ValueError('Use hidden /key input for credentials; secrets are not settings')
            no_secrets(item)
    elif isinstance(value, list):
        for item in value:
            no_secrets(item)


def read(app, target=None):
    if target is None:
        return {'targets': TARGETS, 'modes': ['plan', 'sim', 'real'],
                'permission_profiles': ['default', 'plan', 'cautious', 'yolo'],
                'additional_configuration': {'harness': 'harness_read / harness_write', 'skills': 'skill_list / skill_read / skill_write',
                    'credentials': '/key save (hidden input)', 'launch_paths': '--config / --state-dir / LOOP_HOME: next launch'},
                'write_permission': app.permissions.snapshot()['rules']['settings_update']}
    if target == 'permissions':
        return app.permissions.snapshot()
    if target == 'profiles':
        return {'profiles': app.providers.list(), 'selected': app.providers.selected()}
    path = paths(app)[target]
    value = json.loads(path.read_text()) if path.exists() else None
    if value is not None:
        no_secrets(value)
    result = {'path': str(path), 'value': value}
    if target == 'config':
        result['effective'] = app.config
    return result


def idle(app):
    from terminal.permissions import ApprovalPreconditionError
    if any(r['state'] in ('running', 'queued') for r in app.runtime.records.values()):
        raise ApprovalPreconditionError('Wait for or cancel running subagents before changing configuration')
    from terminal.task_service import status
    if status(app.state_dir)['process_alive']:
        raise ApprovalPreconditionError('Stop the task supervisor before changing configuration')


def update(app, target, value):
    if not isinstance(value, dict):
        raise ValueError('value must be an object')
    no_secrets(value)
    json.dumps(value, allow_nan=False)
    with app.runtime.lock:
        if target == 'permissions':
            if set(value) == {'mode'}:
                app.permissions.set_mode(value['mode'])
            elif set(value) == {'profile'}:
                app.permissions.set_profile(value['profile'])
            elif set(value) == {'action', 'rule'}:
                app.permissions.set_rule(value['action'], value['rule'])
            else:
                raise ValueError('Use {mode}, {profile}, or {action,rule}')
            app.enforce_node_permissions()
            return {'applied': True, **app.permissions.snapshot()}
        idle(app)
        if target == 'profiles':
            operation = value.get('operation')
            required = {'operation', 'name', 'config'} if operation == 'save' else {'operation', 'name'}
            if not required <= set(value) or set(value) - required - ({'replace'} if operation == 'save' else set()):
                raise ValueError('Invalid profile operation fields')
            if operation == 'save':
                validate_provider(value['config'])
                if 'replace' in value and type(value['replace']) is not bool:
                    raise ValueError('replace must be boolean')
                app.providers.save(value['name'], value['config'], value.get('replace', False))
                if value['name'] in app.providers.selected().values():
                    app.apply_profiles(clear_history=False)
            elif operation == 'use':
                app.providers.use('master', value['name'])
                app.apply_profiles(clear_history=False)
            elif operation == 'remove':
                app.providers.remove(value['name'])
            else:
                raise ValueError('Unknown profile operation')
            return {'applied': True, **read(app, target)}
        if target == 'deployment':
            from core.deployment import Deployment
            from terminal.carriers import Carriers, bind, validate_bindings
            if set(value) != {'manifest', 'host_id'}:
                raise ValueError('deployment requires manifest and host_id')
            if any(n['process_alive'] for n in app.nodes.status()['nodes']):
                raise ValueError('Stop owned nodes before changing deployment')
            deployment = Deployment(value['manifest'], value['host_id'])
            validate_bindings(deployment, app.nodes.definitions)
            bind(app.state_dir, deployment)
            app.deployment = deployment
            app.carriers = Carriers(app, deployment)
            return {'applied': True, **app.carriers.listing()}
        path = paths(app)[target]
        encoded = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / 'candidate.json'
            candidate.write_text(encoded, encoding='utf-8')
            if target == 'config':
                # Validate the replacement independently of existing user overrides.
                validate_config(value)
            elif target == 'agents':
                from terminal.agents import AgentRuntime
                definitions = AgentRuntime.load_definitions(candidate, {'run_sim', 'generate_scene'})
                path = loop_home() / 'agents.json'
            elif target == 'task_runtime':
                from terminal.task_supervisor import load_policy
                load_policy(candidate, {t['function']['name'] for t in app.agent.tools} - NAMES)
                path = app.state_dir / 'task_runtime.json'
        receipt = atomic_text(app, path, encoded)
        if target == 'agents':
            app.runtime.definitions = definitions
        return {'saved': True, 'path': str(path), 'backup': receipt['backup'], 'applied': target == 'agents',
                'effective_after': 'now' if target == 'agents' else 'next supervisor start' if target == 'task_runtime' else 'next Loop start; explicit config overrides this file; saved profiles remain authoritative'}


def validate_config(value):
    defaults = json.loads((ROOT / 'configs/config.example.json').read_text())
    if set(value) - set(defaults):
        raise ValueError('Unknown config section')
    for section, fields in value.items():
        if not isinstance(fields, dict):
            raise ValueError('Config sections must be objects')
        if section in ('llm', 'expert'):
            validate_provider({**defaults['llm'], **fields})
        elif section == 'resources':
            from core.resources import validate_policy
            validate_policy(fields)
        elif section == 'scene':
            if set(fields) - {'backend'} or fields.get('backend', 'mujoco') != 'mujoco':
                raise ValueError('Only mujoco scene backend is implemented')
        elif section == 'services':
            for name, spec in fields.items():
                if name not in defaults['services'] or not isinstance(spec, dict) or not {'argv', 'cwd'} <= set(spec) or set(spec) - {'argv', 'cwd', 'resources'}:
                    raise ValueError('Services require pi05/act with argv and cwd')
                if 'resources' in spec:
                    from core.resources import validate_request
                    validate_request(spec['resources'])
                if not isinstance(spec['argv'], list) or not all(isinstance(s, str) for s in spec['argv']) or not (spec['cwd'] is None or isinstance(spec['cwd'], str)):
                    raise ValueError('Invalid service argv/cwd')


def call(app, name, args):
    allowed = {'target'} if name == 'settings_read' else {'target', 'value'}
    if not isinstance(args, dict) or set(args) - allowed or (name == 'settings_update' and set(args) != allowed) or ('target' in args and args['target'] not in TARGETS):
        raise ValueError('Invalid settings arguments')
    app.permissions.check(name, args)
    return read(app, args.get('target')) if name == 'settings_read' else update(app, args['target'], args['value'])
