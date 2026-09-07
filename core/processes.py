"""Bounded process-control requests; OS inspection belongs to the adapter."""
import re


def request(action, value):
    allowed = {'host', 'ports', 'pids'} if action == 'inspect' else {'host', 'ports', 'targets', 'mode', 'wait_s'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('Invalid process-control fields')
    result = dict(value)
    host = result.setdefault('host', 'local')
    if not isinstance(host, str) or not re.fullmatch(r'(?:[A-Za-z0-9_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9.-]*', host):
        raise ValueError('host must be local or an SSH alias/user@hostname; no shell options')
    for name, maximum in (('ports', 65535), ('pids', 2147483647)):
        if name not in allowed:
            continue
        values = result.setdefault(name, [])
        if not isinstance(values, list) or len(values) > 32 or any(type(x) is not int or not 1 <= x <= maximum for x in values):
            raise ValueError('Expected at most 32 valid ' + name)
        result[name] = sorted(set(values))
    if action == 'stop':
        targets = result.get('targets')
        if not isinstance(targets, list) or not 1 <= len(targets) <= 32:
            raise ValueError('Stop requires 1..32 exact targets from process_inspect')
        for item in targets:
            if not isinstance(item, dict) or set(item) != {'pid', 'start_ticks', 'boot_id'}:
                raise ValueError('Each target needs pid, start_ticks and boot_id from inspection')
            if type(item['pid']) is not int or item['pid'] <= 1 or type(item['start_ticks']) is not int or item['start_ticks'] < 1:
                raise ValueError('Invalid process identity')
            if not isinstance(item['boot_id'], str) or not re.fullmatch(r'[0-9a-f-]{36}', item['boot_id']):
                raise ValueError('Invalid host boot identity')
        if len({item['pid'] for item in targets}) != len(targets):
            raise ValueError('Each PID must appear only once')
        mode = result.setdefault('mode', 'graceful')
        if mode not in ('graceful', 'terminate', 'kill', 'escalate'):
            raise ValueError('mode: graceful / terminate / kill / escalate')
        wait = result.setdefault('wait_s', 3)
        if type(wait) not in (int, float) or not .1 <= wait <= 10:
            raise ValueError('wait_s must be 0.1..10 per signal')
        result['signals'] = {'graceful': ['SIGINT'], 'terminate': ['SIGTERM'],
                             'kill': ['SIGKILL'], 'escalate': ['SIGINT', 'SIGTERM', 'SIGKILL']}[mode]
    result['action'] = action
    return result
