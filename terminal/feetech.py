"""Feetech diagnostic tools; motion primitives are not agent tools."""
import json
import uuid
from toolchain import feetech
from terminal.files import schema

TOOLS = [
    schema('feetech_environment', 'Inspect this Python for pyserial and packaged Feetech capabilities. No connection.', {}, []),
    schema('feetech_scan', 'Detect Feetech bus servo baudrates/IDs using binary PING and model READ. Transmits queries only, never moves/enables motors. Enumerate devices to select a real port first. Default IDs 1..20; negatives only cover scanned IDs/bauds.',
           {'port': {'type': 'string'}, 'ids': {'type': 'array', 'items': {'type': 'integer'}},
            'baudrates': {'type': 'array', 'items': {'type': 'integer'}}}, ['port']),
    schema('feetech_read', 'Read verified STS3215 state at a detected ID and baudrate. Unknown models are reported without guessing registers. No actuation.',
           {'port': {'type': 'string'}, 'motor_id': {'type': 'integer'}, 'baudrate': {'type': 'integer'}},
           ['port', 'motor_id', 'baudrate']),
]
NAMES = {tool['function']['name'] for tool in TOOLS}


def dispatch(app, name, args):
    allowed = {'feetech_environment': set(), 'feetech_scan': {'port', 'ids', 'baudrates'},
               'feetech_read': {'port', 'motor_id', 'baudrate'}}
    if not isinstance(args, dict) or set(args) - allowed[name]:
        raise ValueError('Unexpected Feetech arguments')
    if name == 'feetech_environment':
        return feetech.environment()
    from core.store import EventStore
    # Reuse the project's Episode/Review evidence types, independent of model prose.
    from core.contracts import Episode, Review, record as serialize
    directory = app.state_dir / 'feetech'
    directory.mkdir(parents=True, exist_ok=True)
    operation_id = uuid.uuid4().hex
    try:
        if name == 'feetech_scan':
            result = feetech.scan(**args, stop_event=app.stop_event)
        else:
            with feetech.Bus(args['port'], args['baudrate']) as bus:
                result = bus.read_state(args['motor_id'])
            result.update(port=args['port'], register_writes=False,
                          verdict='pass' if result.get('state_read') else 'inconclusive')
    except Exception as exc:
        result = {'error': type(exc).__name__, 'message': str(exc), 'verdict': 'inconclusive',
                  'register_writes': False, 'retryable': False}
    path = directory / (operation_id + '.json')
    path.write_text(json.dumps({'tool': name, 'arguments': args, 'result': result}, ensure_ascii=False, indent=2))
    store = EventStore(directory / 'evidence.sqlite')
    try:
        episode = Episode(operation_id, 1, 'feetech-diagnostics', 'hardware-query',
                          actions=[{'tool': name, 'arguments': args}], observations=[{'report': str(path)}])
        store.append('episode', serialize(episode))
        review = Review(result['verdict'], 1. if result['verdict'] == 'pass' else 0.,
                        'Serial diagnostic evidence only; no motor movement or physical task success established')
        store.append('review', serialize(review))
    finally:
        store.close()
    return {**result, 'report': str(path), 'review': serialize(review)}
