"""Explicit carrier routing through existing local node permissions and receipts."""
import json
from pathlib import Path
import re
import shlex
import uuid
from core.deployment import Deployment
from terminal.files import schema

HELP = '''/carrier list                         Show deployment and carrier capabilities
/carrier status ID                    Inspect current instance and command receipts
/carrier start ID                     Start a configured local carrier node
/carrier move ID INSTANCE Q1 Q2        Queue a simulated move bound to this instance
/carrier stop ID INSTANCE              Stop this exact instance; not a hardware emergency stop
Remote assignments are listed but never executed by this host. No carrier starts automatically.'''
TOOLS = [
    schema('carrier_list', 'List deployment carriers with local/remote assignment and actual installed adapter capabilities.', {}, []),
    schema('carrier_status', 'Read a local carrier instance, fresh heartbeat and command receipts. Remote declarations are not live state.', {'carrier_id': {'type': 'string'}}, ['carrier_id']),
    schema('carrier_start', 'Start a configured local carrier using existing node permissions. Never moves on start; inspect status before commands.', {'carrier_id': {'type': 'string'}}, ['carrier_id']),
    schema('carrier_command', 'Queue a command to an exact carrier instance. Reuse request_id for retry of the same request; queued is not task success. Only installed sim_arm move is supported.',
           {'carrier_id': {'type': 'string'}, 'instance_id': {'type': 'string'}, 'request_id': {'type': 'string'},
            'action': {'type': 'string', 'enum': ['move']}, 'arguments': {'type': 'object', 'properties': {'target': {'type': 'array', 'items': {'type': 'number'}, 'minItems': 2, 'maxItems': 2}}, 'required': ['target'], 'additionalProperties': False}},
           ['carrier_id', 'instance_id', 'request_id', 'action', 'arguments']),
    schema('carrier_stop', 'Stop only the specified carrier instance; rejects stale instance IDs.',
           {'carrier_id': {'type': 'string'}, 'instance_id': {'type': 'string'}}, ['carrier_id', 'instance_id']),
]
NAMES = {t['function']['name'] for t in TOOLS}
# Capability metadata describes implemented adapters, never arbitrary manifest claims.
CAPABILITIES = {'sim_arm': {'simulated': True, 'commands': ['move'], 'units': 'radians', 'model': 'packaged two_joint.xml', 'controls_viewer': False},
                'serial_rx': {'simulated': False, 'commands': [], 'hardware_writes': False, 'mode': 'receive_only'}}


class Carriers:
    def __init__(self, app, deployment=None):
        self.app, self.deployment = app, deployment
        self.requests = {}
        self.instances = {}

    @staticmethod
    def node_name(carrier_id):
        return 'carrier-' + carrier_id

    def descriptor(self, item):
        local = item['host'] == self.deployment.host_id
        supported = local and item['adapter'] in self.app.nodes.definitions and item['adapter'] in CAPABILITIES
        return {'carrier_id': item['id'], 'host_id': item['host'], 'label': item['label'], 'adapter': item['adapter'],
                'local': local, 'supported_here': supported, 'capabilities': CAPABILITIES.get(item['adapter'], {}) if supported else {},
                'availability': 'local' if supported else 'remote_unconnected' if not local else 'adapter_not_installed'}

    def listing(self):
        if not self.deployment:
            return {'configured': False, 'carriers': [], 'hint': 'Start with --deployment FILE --host HOST_ID'}
        return {'configured': True, 'deployment_id': self.deployment.deployment_id, 'host_id': self.deployment.host_id,
                'profile_sha256': self.deployment.fingerprint, 'remote_transport': 'not_implemented',
                'carriers': [self.descriptor(item) for item in self.deployment.carriers.values()]}

    def call(self, name, args):
        definition = next(t['function']['parameters'] for t in TOOLS if t['function']['name'] == name)
        if not isinstance(args, dict) or set(args) - set(definition['properties']) or not set(definition['required']) <= set(args):
            raise ValueError('Invalid carrier tool arguments')
        self.app.permissions.check(name, args)
        if name == 'carrier_list':
            return self.listing()
        if not self.deployment:
            raise ValueError('No deployment configured')
        item = self.deployment.carrier(args['carrier_id'], local=True)
        descriptor = self.descriptor(item)
        if not descriptor['supported_here']:
            raise ValueError('Carrier adapter is not installed; declarations do not supply a driver')
        node = self.node_name(item['id'])
        # Compare identity and dispatch under the same runtime lock, including permission checks.
        with self.app.nodes.lock:
            if name == 'carrier_start':
                state = self.app.tool('node_start', {'name': node, 'kind': item['adapter'], 'config': item['config']})
                self.instances[item['id']] = state['instance_id']
                return {**descriptor, 'node': state}
            if node not in self.app.nodes.records:
                if name == 'carrier_status':
                    return {**descriptor, 'node': {'state': 'not_started', 'heartbeat_fresh': False}}
                raise ValueError('Carrier has not been started')
            state = self.app.tool('node_status', {'name': node})
            if self.instances.get(item['id']) != state['instance_id']:
                raise ValueError('Node name belongs to an instance not started by this carrier router')
            if name == 'carrier_status':
                return {**descriptor, 'node': state}
            if args['instance_id'] != state['instance_id']:
                raise ValueError('Carrier instance changed; inspect current status before a new command')
            if name == 'carrier_stop':
                return {**descriptor, 'node': self.app.tool('node_stop', {'name': node})}
            if args['action'] not in descriptor['capabilities']['commands']:
                raise ValueError('Command is not supported by this carrier')
            request = args['request_id']
            if not isinstance(request, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', request):
                raise ValueError('request_id must be 1..64 letters, digits, _ or -')
            key = (item['id'], state['instance_id'], request)
            payload = json.dumps(args, sort_keys=True, allow_nan=False)
            if key in self.requests:
                previous, result = self.requests[key]
                if previous != payload:
                    raise ValueError('request_id already used with different arguments')
                return {**result, 'duplicate': True}
            if len(self.requests) >= 4096:
                raise ValueError('Carrier request ledger is full for this terminal; start a new session')
            # Reserve before execution so an exception after enqueue cannot replay a command.
            unknown = {**descriptor, 'request_id': request, 'state': 'inconclusive',
                       'task_success': 'not_evaluated', 'next_step': 'Inspect carrier status before any new request'}
            self.requests[key] = (payload, unknown)
            result = {**descriptor, 'request_id': request,
                      **self.app.tool('node_command', {'name': node, 'action': args['action'], 'arguments': args['arguments']})}
            self.requests[key] = (payload, result)
            return result


def dispatch(app, text):
    parts = shlex.split(text)
    if not parts or parts == ['list']:
        return json.dumps(app.tool('carrier_list', {}), ensure_ascii=False)
    if parts == ['help']:
        return HELP
    if len(parts) == 2 and parts[0] in ('start', 'status'):
        args = {'carrier_id': parts[1]}
        return json.dumps(app.tool('carrier_' + parts[0], args), ensure_ascii=False)
    if len(parts) == 3 and parts[0] == 'stop':
        return json.dumps(app.tool('carrier_stop', {'carrier_id': parts[1], 'instance_id': parts[2]}), ensure_ascii=False)
    if len(parts) == 5 and parts[0] == 'move':
        return json.dumps(app.tool('carrier_command', {'carrier_id': parts[1], 'instance_id': parts[2], 'request_id': uuid.uuid4().hex,
                         'action': 'move', 'arguments': {'target': [float(v) for v in parts[3:]]}}), ensure_ascii=False)
    raise ValueError(HELP)


def validate_bindings(deployment, definitions):
    resources = set()
    for item in deployment.carriers.values():
        if item['host'] != deployment.host_id or item['adapter'] not in definitions:
            continue
        definition = definitions[item['adapter']]
        config = definition.validate(item['config'])
        resource = definition.resource(config, Carriers.node_name(item['id']))
        if resource in resources:
            raise ValueError('Multiple local carriers claim the same resource')
        resources.add(resource)


def load_bound(state):
    path = Path(state) / 'deployment.json'
    if not path.exists():
        return None
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Deployment binding exceeds 1 MiB')
    data = json.loads(path.read_text(encoding='utf-8'))
    return Deployment(data['manifest'], data['host_id'])


def bind(state, deployment):
    """Called under the CLI's deployment binding lock before App initialization."""
    path = Path(state) / 'deployment.json'
    existing = load_bound(state)
    if existing and (existing.deployment_id, existing.host_id) != (deployment.deployment_id, deployment.host_id):
        raise ValueError('State directory belongs to another deployment/host; choose a separate state directory')
    if (existing is None or existing.manifest != deployment.manifest) and (Path(state) / 'tasks.sqlite').exists():
        from terminal.task_service import status
        if status(state)['process_alive']:
            raise ValueError('Stop the task supervisor before changing deployment bindings')
    if existing and existing.manifest == deployment.manifest:
        return
    from terminal.coding import atomic_text
    from types import SimpleNamespace
    atomic_text(SimpleNamespace(state_dir=Path(state)), path,
                json.dumps({'host_id': deployment.host_id, 'manifest': deployment.manifest}, ensure_ascii=False, indent=2))
