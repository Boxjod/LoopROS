"""Interpret explicit connection receipts, not prose, ports or process exit codes."""
from loop_robot.core.tasks import assess


def observation(result):
    if not isinstance(result, dict):
        return None
    connection = result.get('connection')
    prefix = 'connection.'
    if connection is None and isinstance(result.get('output'), dict):
        connection = result['output'].get('connection')
        prefix = 'output.connection.'
    if not isinstance(connection, dict) or type(connection.get('connected')) is not bool:
        return None
    # Explicit identity prevents mixing different robots from a shared word in a goal.
    required = ('device', 'host', 'transport')
    if any(not isinstance(connection.get(k), str) or not connection[k].strip() or len(connection[k]) > 200 or not connection[k].isprintable() for k in required):
        return None
    config = {k: connection[k] for k in required}
    for key in ('username', 'port', 'method'):
        value = connection.get(key)
        if isinstance(value, str) and value.isprintable() and len(value) <= 200:
            config[key] = value
        elif key == 'port' and type(value) is int and 1 <= value <= 65535:
            config[key] = value
    config['transport'] = config['transport'].casefold()
    config['device'] = config['device'].casefold()
    return config, connection['connected'], prefix


def remember_success(learning, receipts, checks, source, verified):
    if not verified:
        return
    for receipt in receipts:
        result = receipt.get('result')
        parsed = observation(result)
        if not parsed or result.get('error') or result.get('returncode') not in (None, 0) or result.get('stop_reason'):
            continue
        config, connected, prefix = parsed
        # A task succeeding on an unrelated check must not verify connectivity.
        relevant = [c for c in checks if c['tool'] == receipt['tool'] and c['path'] == prefix + 'connected' and c['equals'] is True]
        if connected and any(assess([check], [receipt])['verdict'] == 'pass' for check in relevant):
            recorded_at = learning.store.read(learning.scope(), source)['updated']
            learning.layers.connection_success(learning.scope(), learning.clean(config), source, recorded_at)


def fallback(learning, result):
    parsed = observation(result)
    if not parsed or parsed[1]:
        return None
    if not learning.can_recall():
        return None
    config, _, _ = parsed
    previous = learning.layers.last_connection(learning.scope(), config['device'], config['transport'])
    if not previous or all(previous['config'].get(key) == value for key, value in config.items()):
        return None
    return {'type': 'previous_success_available', 'failed_config': learning.clean(config), 'last_success': previous,
            'user_confirmation_required': True, 'automatic_retry': False,
            'next_step': 'Report the failed current configuration and ask whether to try this last successful configuration. Do not switch until the user agrees.'}
