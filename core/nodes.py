"""Local, long-lived process supervision. Standard library only; no device imports.

A node name identifies a service; instance_id identifies one run, pid its process.
Factories are trusted Python registrations, never shell commands from a model.
"""
from collections import deque
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass
import json
import multiprocessing
from pathlib import Path
import re
import threading
import time
import uuid


@dataclass(frozen=True)
class NodeDefinition:
    factory: object
    validate: object
    resource: object
    stop_timeout_s: float = .5


def _worker(pipe, stopping, factory, config):
    from release_runtime import runtime_session
    with runtime_session(), Path(config['evidence_path']).with_suffix('.log').open('a', encoding='utf-8', buffering=1) as output:
        with redirect_stdout(output), redirect_stderr(output):
            _run_worker(pipe, stopping, factory, config)


def _run_worker(pipe, stopping, factory, config):
    service = None
    try:
        service = factory(config)
        last = 0.0
        while not stopping.is_set():
            if pipe.poll():
                request = pipe.recv()
                try:
                    if time.monotonic() > request['expires_at']:
                        raise TimeoutError('Command expired before execution')
                    result = service.command(request['action'], request['arguments'], stopping)
                    pipe.send({'type': 'result', 'command_id': request['command_id'], 'result': result})
                except Exception as exc:
                    pipe.send({'type': 'result', 'command_id': request['command_id'],
                               'result': {'error': type(exc).__name__, 'message': str(exc)[:1000]}})
            service.tick()
            now = time.monotonic()
            if now - last >= .2:
                pipe.send({'type': 'heartbeat', 'observed_at': now, 'snapshot': service.snapshot()})
                last = now
            stopping.wait(.02)
    except (EOFError, BrokenPipeError):
        pass  # Owner exited: never keep controlling an orphaned body.
    except Exception as exc:
        try:
            pipe.send({'type': 'failed', 'error': type(exc).__name__ + ': ' + str(exc)[:1000]})
        except (OSError, EOFError):
            pass
    finally:
        if service is not None:
            service.close()
        pipe.close()


class NodeRuntime:
    def __init__(self, definitions, directory, max_nodes=8, stale_after=3.0, admission=None):
        self.admission = admission
        self.definitions = dict(definitions)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_nodes, self.stale_after = max_nodes, stale_after
        self.records, self.resources = {}, {}
        self.lock = threading.RLock()
        self.context = multiprocessing.get_context('spawn')
        self.closed = False
        self.wake = threading.Event()
        self.monitor = threading.Thread(target=self._monitor, name='loop-node-supervisor', daemon=True)
        self.monitor.start()

    def _event(self, record, kind, **data):
        event = {'time': time.time(), 'node': record['name'], 'instance_id': record['instance_id'],
                 'kind': kind, **data}
        record['events'].append(event)
        with (self.directory / 'events.jsonl').open('a', encoding='utf-8') as output:
            output.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')

    def start(self, name, kind, config=None):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}', name) or name.lower() == 'master':
            raise ValueError('Use a unique node name (1..40 letters, digits, _ or -; master is reserved)')
        if kind not in self.definitions:
            raise ValueError('Unknown node kind; registered kinds: ' + ', '.join(self.definitions))
        definition = self.definitions[kind]
        config = definition.validate({} if config is None else config)
        config = json.loads(json.dumps(config, allow_nan=False))
        resource = definition.resource(config, name)
        with self.lock:
            if self.closed:
                raise RuntimeError('Node runtime closed')
            self._poll()
            existing = self.records.get(name)
            if existing and existing['process'].is_alive():
                raise ValueError('Node name already running')
            if resource in self.resources:
                raise ValueError('Resource already owned by node ' + self.resources[resource])
            if sum(r['process'].is_alive() for r in self.records.values()) >= self.max_nodes:
                raise RuntimeError('Node process limit reached')
            if name not in self.records and len(self.records) >= 64:
                raise RuntimeError('Node name budget reached')
            instance = uuid.uuid4().hex
            config.update(node_name=name, instance_id=instance,
                          evidence_path=str(self.directory / (instance + '.sqlite')))
            parent, child = self.context.Pipe()
            stopping = self.context.Event()
            process = self.context.Process(target=_worker, args=(child, stopping, definition.factory, config),
                                           name='loop-node-' + name, daemon=True)
            token = None
            try:
                if self.admission:
                    from core.resources import ResourceBusy
                    token = self.admission.inspect(acquire=True, workload='node', request={})
                    if token is None:
                        raise ResourceBusy('Waiting for resources: ' + self.admission.last['reason'])
                process.start()
                if token: self.admission.bind(token, process.pid)
            except BaseException:
                if process.pid is not None:
                    if process.is_alive(): process.terminate()
                    process.join(timeout=1)
                    if process.is_alive():
                        process.kill()
                        process.join(timeout=1)
                if token: self.admission.release(token)
                parent.close()
                child.close()
                raise
            child.close()
            record = {'lease': token, 'name': name, 'kind': kind, 'instance_id': instance, 'process': process,
                      'pipe': parent, 'stopping': stopping, 'state': 'starting', 'snapshot': {},
                      'heartbeat': None, 'started': time.monotonic(), 'error': None, 'resource': resource,
                      'pending': {}, 'results': deque(maxlen=32), 'events': deque(maxlen=100),
                      'evidence_path': config['evidence_path'], 'reaped': False}
            self.records[name] = record
            self.resources[resource] = name
            self._event(record, 'started', pid=process.pid, node_kind=kind, resource=resource)
            return self._status(record)

    def _status(self, record):
        alive = record['process'].is_alive()
        heartbeat = record['heartbeat']
        age = time.monotonic() - heartbeat if heartbeat is not None else None
        fresh = alive and age is not None and 0 <= age < self.stale_after
        state = record['state']
        if alive and state not in ('failed', 'stopping'):
            state = 'running' if fresh else ('starting' if heartbeat is None and time.monotonic() - record['started'] < self.stale_after else 'unresponsive')
        return {'name': record['name'], 'kind': record['kind'], 'instance_id': record['instance_id'],
                'pid': record['process'].pid, 'process_alive': alive, 'state': state,
                'heartbeat_fresh': fresh, 'heartbeat_age_s': age, 'resource': record['resource'],
                'snapshot': record['snapshot'], 'pending_commands': list(record['pending']),
                'results': list(record['results']), 'error': record['error'],
                'evidence_path': record['evidence_path'],
                'output_log': str(Path(record['evidence_path']).with_suffix('.log'))}

    def status(self, name=None):
        with self.lock:
            self._poll()
            value = self._status(self.records[name]) if name is not None else {
                'kinds': list(self.definitions), 'nodes': [self._status(r) for r in self.records.values()]}
            return json.loads(json.dumps(value))

    def command(self, name, action, arguments=None):
        arguments = {} if arguments is None else arguments
        if not isinstance(action, str) or not isinstance(arguments, dict):
            raise ValueError('Expected action string and arguments object')
        with self.lock:
            self._poll()
            record = self.records[name]
            if self._status(record)['state'] != 'running':
                raise RuntimeError('Node is not ready or its heartbeat is stale')
            if record['pending']:
                raise RuntimeError('A node command is still pending; inspect status or stop the node')
            command_id = uuid.uuid4().hex
            request = {'command_id': command_id, 'action': action, 'arguments': arguments,
                       'expires_at': time.monotonic() + 5}
            if len(json.dumps(request, allow_nan=False)) > 4096:
                raise ValueError('Node command exceeds 4096 characters')
            record['pipe'].send(request)
            record['pending'][command_id] = time.monotonic()
            self._event(record, 'command', command_id=command_id, action=action, arguments=arguments)
            return {'name': name, 'instance_id': record['instance_id'], 'command_id': command_id,
                    'state': 'queued', 'task_success': 'not_evaluated'}

    def _poll(self):
        for record in self.records.values():
            if record['reaped']:
                continue
            try:
                for _ in range(64):
                    if not record['pipe'].poll():
                        break
                    item = record['pipe'].recv()
                    if item['type'] == 'heartbeat':
                        record['heartbeat'] = item['observed_at']
                        record['snapshot'] = item['snapshot']
                    elif item['type'] == 'result':
                        record['pending'].pop(item['command_id'], None)
                        record['results'].append(item)
                        self._event(record, 'result', **{k: v for k, v in item.items() if k != 'type'})
                    elif item['type'] == 'failed':
                        record.update(state='failed', error=item['error'])
            except (EOFError, OSError):
                pass
            if not record['process'].is_alive():
                record['process'].join(timeout=0)
                record['pipe'].close()
                record['reaped'] = True
                if record.get('lease'):
                    self.admission.release(record.pop('lease'))
                if record['state'] != 'stopped':
                    record['state'] = 'failed'
                    record['error'] = record['error'] or 'Node exited unexpectedly'
                for command_id in record['pending']:
                    result = {'command_id': command_id, 'result': {'verdict': 'inconclusive', 'error': 'Node exited before command completion'}}
                    record['results'].append(result)
                    self._event(record, 'result', **result)
                    # The child has exited. Record missing completion evidence without
                    # replaying the command, even if its earlier intent was persisted.
                    from core.contracts import Episode, Review, record as encode
                    from core.store import EventStore
                    evidence = EventStore(record['evidence_path'])
                    try:
                        episode = Episode(command_id, 1, record['name'], 'unavailable',
                                          error='Node exited before command completion')
                        evidence.append('episode', encode(episode))
                        evidence.append('review', encode(Review('inconclusive', 0, episode.error)))
                    finally:
                        evidence.close()
                record['pending'].clear()
                self.resources.pop(record['resource'], None)
                self._event(record, 'exited', state=record['state'], exitcode=record['process'].exitcode,
                            error=record['error'])

    def _monitor(self):
        while not self.wake.wait(.05):
            with self.lock:
                self._poll()

    def logs(self, name, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Log limit must be 1..100')
        with self.lock:
            self._poll()
            return list(self.records[name]['events'])[-limit:]

    def stop(self, name):
        with self.lock:
            record = self.records[name]
            if not record['reaped']:
                record['state'] = 'stopping'
                record['stopping'].set()
                process = record['process']
                process.join(timeout=self.definitions[record['kind']].stop_timeout_s)
                forced = process.is_alive()
                if forced:
                    process.terminate()
                    process.join(timeout=.5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=.5)
                record['state'] = 'stopped' if not process.is_alive() else 'failed'
                self._event(record, 'stop', forced=forced)
                self._poll()
            return self._status(record)

    def close(self):
        with self.lock:
            self.closed = True
            for name in list(self.records):
                self.stop(name)
        self.wake.set()
        self.monitor.join(timeout=1)
