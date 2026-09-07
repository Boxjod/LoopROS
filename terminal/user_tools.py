"""Portable, inspectable Python tools owned by the Loop user."""
import ast
import hashlib
import json
from pathlib import Path
import re
import tempfile
from terminal.files import schema
from terminal.home import initialize
from terminal.coding import atomic_text, resolve

TOOLS = [
    schema('tool_read', 'List user-authored portable tools, or read one with its source, usage and sha256 before execution.', {'name': {'type': 'string'}}, []),
    schema('tool_write', 'Create/update a reusable Python tool in Loop home. source reads CLI arguments from sys.argv; print JSON for structured output. Connection probes should return connection:{device,host,transport,username,port,method,connected}; connected must reflect actual authenticated connection verification, not an open port or process start. Use output.connection.connected in task acceptance when executing with tool_run. Syntax checked without execution. Existing tools require expected_sha256 from tool_read. No automatic dependency installation or permission grant.',
           {'name': {'type': 'string'}, 'description': {'type': 'string'}, 'source': {'type': 'string'}, 'expected_sha256': {'type': 'string'}}, ['name', 'description', 'source']),
    schema('tool_run', 'Run the inspected version of a user tool. Requires tool_run permission; an explicit run_python deny also blocks execution. Returns real exit code, stdout, stderr, report and parsed JSON output when available. Host privileges, not a sandbox; arguments are CLI strings, cwd is current workspace.',
           {'name': {'type': 'string'}, 'expected_sha256': {'type': 'string'}, 'arguments': {'type': 'array', 'items': {'type': 'string'}}, 'timeout_s': {'type': 'integer'}}, ['name', 'expected_sha256']),
    schema('python_check', 'Parse/compile a workspace Python file without executing or importing it. Returns syntax errors with line/column and imported module names. Does not prove runtime correctness or dependency availability.', {'path': {'type': 'string'}}, ['path']),
]
NAMES = {t['function']['name'] for t in TOOLS}


def target(name):
    if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', name):
        raise ValueError('Tool name: 1..48 lowercase letters, digits, _ or -, starting with a letter')
    root = initialize().resolve()
    path = root / 'tools' / (name + '.json')
    if not path.resolve().is_relative_to(root) or path.is_symlink() or path.parent.is_symlink():
        raise PermissionError('User tools must remain inside Loop home without symlinks')
    return path


def inspect(name):
    path = target(name)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Tool exceeds 1 MiB')
    raw = path.read_bytes()
    value = json.loads(raw)
    if set(value) != {'name', 'description', 'source', 'version'} or value['name'] != name or value['version'] != 1 or not isinstance(value['source'], str) or not isinstance(value['description'], str):
        raise ValueError('Invalid tool package')
    return {**value, 'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}


def syntax(source, filename):
    try:
        tree = ast.parse(source, filename=filename)
        compile(tree, filename, 'exec')
    except SyntaxError as exc:
        return {'valid': False, 'executed': False, 'error': 'SyntaxError', 'message': exc.msg,
                'line': exc.lineno, 'column': exc.offset, 'text': exc.text}
    imports = sorted({alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names} |
                     {node.module or '' for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)})
    return {'valid': True, 'executed': False, 'imports': imports, 'runtime_verified': False}


def call(app, name, args):
    definition = next(t['function']['parameters'] for t in TOOLS if t['function']['name'] == name)
    if not isinstance(args, dict) or set(args) - set(definition['properties']) or not set(definition['required']) <= set(args):
        raise ValueError('Invalid user tool arguments')
    app.permissions.check(name, args)
    if name == 'python_check':
        path = resolve(app, args['path'])
        if path.suffix != '.py' or path.stat().st_size > 1024 * 1024:
            raise ValueError('Expected a Python file of at most 1 MiB')
        raw = path.read_bytes()
        return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), **syntax(raw.decode('utf-8'), str(path))}
    if name == 'tool_read':
        if 'name' in args:
            return inspect(args['name'])
        root = initialize() / 'tools'
        names = sorted(p.stem for p in root.glob('*.json'))[:100]
        return {'directory': str(root), 'tools': [{k: v for k, v in inspect(n).items() if k != 'source'} for n in names]}
    path = target(args['name'])
    if name == 'tool_write':
        if not isinstance(args['description'], str) or not 1 <= len(args['description']) <= 2000 or not isinstance(args['source'], str) or len(args['source']) > 200000:
            raise ValueError('Tool requires a short description and Python source up to 200000 characters')
        check = syntax(args['source'], args['name'] + '.py')
        if not check['valid']:
            return check
        value = {k: args[k] for k in ('name', 'description', 'source')}
        value['version'] = 1
        receipt = atomic_text(app, path, json.dumps(value, ensure_ascii=False, indent=2), args.get('expected_sha256'), require_hash=True)
        return {**receipt, 'name': args['name'], 'syntax': check, 'reload': 'next tool_read/tool_run; no restart'}
    spec = inspect(args['name'])
    if args['expected_sha256'] != spec['sha256']:
        raise ValueError('Tool changed; inspect it again before execution')
    # Gate the stable, inspectable package identity rather than a transient script path.
    if app.permissions.snapshot()['rules']['run_python'] == 'deny':
        raise PermissionError('Python execution is denied by run_python')
    from terminal.python_runner import run
    with tempfile.TemporaryDirectory(prefix='loop-tool-') as folder:
        script = Path(folder) / (args['name'] + '.py')
        script.write_text(spec['source'], encoding='utf-8')
        run_args = {'path': str(script), 'expected_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
                    **{k: args[k] for k in ('arguments', 'timeout_s') if k in args}}
        result = run(app, run_args, _trusted_path=script)
    result['tool'] = args['name']
    result['tool_sha256'] = spec['sha256']
    result['source_path'] = str(path)
    if result['returncode'] == 0 and not result['stop_reason'] and not result['truncated']:
        try:
            result['output'] = json.loads(result['stdout'])
        except ValueError:
            pass
    Path(result['report']).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
