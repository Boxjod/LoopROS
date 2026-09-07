"""Explicit, permission-gated Python execution. Process limits are not a sandbox."""
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from terminal.files import schema

TOOLS = [schema('run_python',
    'Actually run an existing workspace .py file with this Loop Python, without a shell. Use the current inspected sha256. Syntax is checked locally before launch; a separate python_check call is unnecessary for normal execution. Returns stdout, stderr, exit code and cancellation/timeout evidence. Page stdout_path/stderr_path with read_file for long output instead of rerunning. Runs with host user privileges, not a sandbox. Prefer feetech_scan/read for servo diagnostics.',
    {'path':{'type':'string'}, 'expected_sha256':{'type':'string'},
     'arguments':{'type':'array','items':{'type':'string'}}, 'timeout_s':{'type':'integer'}},
    ['path','expected_sha256'])]
NAMES = {'run_python'}


def run(app, args, _trusted_path=None):
    from terminal.coding import resolve
    from core.store import EventStore
    from core.contracts import Episode, Review, record
    if not isinstance(args,dict) or set(args)-{'path','expected_sha256','arguments','timeout_s'}:
        raise ValueError('Unexpected Python execution arguments')
    path=_trusted_path if _trusted_path is not None else resolve(app,args.get('path',''),write=True)
    if path.suffix!='.py' or not path.is_file() or path.stat().st_size>1024*1024:
        raise ValueError('An existing workspace .py file of at most 1 MiB is required')
    source=path.read_bytes()
    digest=hashlib.sha256(source).hexdigest()
    if args.get('expected_sha256')!=digest:
        raise ValueError('Read the script and supply its current sha256 before execution')
    try:
        compile(source, str(path), 'exec')
    except SyntaxError as exc:
        raise ValueError('Python syntax check failed at line {}: {}'.format(exc.lineno, exc.msg)) from None
    argv=args.get('arguments',[]);timeout=args.get('timeout_s',30)
    if not isinstance(argv,list) or len(argv)>64 or any(not isinstance(s,str) or len(s)>4096 or '\x00' in s for s in argv):
        raise ValueError('arguments must be at most 64 strings, each at most 4096 characters')
    if type(timeout) is not int or not 1<=timeout<=120:
        raise ValueError('timeout_s must be 1..120')
    if app.stop_event.is_set():
        raise RuntimeError('Cancelled before Python execution')
    identifier=uuid.uuid4().hex
    folder=app.state_dir/'python';folder.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-u',str(path),*argv]
    # Do not automatically forward provider credentials to generated programs.
    keep={'PATH','HOME','USER','LOGNAME','LANG','LC_ALL','TMPDIR','TEMP','TMP','SYSTEMROOT','WINDIR','USERPROFILE','LOCALAPPDATA'}
    env={k:v for k,v in os.environ.items() if k.upper() in keep}
    started=time.monotonic();reason=None;process=None
    resources = getattr(app, 'resources', None)
    allocation = resources.lease('python', {}) if resources else nullcontext()
    with allocation:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            try:
                process=subprocess.Popen(command,cwd=app.workspace_root,env=env,stdin=subprocess.DEVNULL,
                                         stdout=output,stderr=errors,start_new_session=os.name=='posix')
                while process.poll() is None:
                    if app.stop_event.is_set():reason='cancelled'
                    elif time.monotonic()-started>=timeout:reason='timeout'
                    elif os.fstat(output.fileno()).st_size+os.fstat(errors.fileno()).st_size>1024*1024:reason='output_limit'
                    if reason:break
                    time.sleep(.025)
            finally:
                if process is not None:
                    if os.name=='posix':
                        try:os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                    elif process.poll() is None:process.kill()
                    process.wait()
            output_sizes = {'stdout':os.fstat(output.fileno()).st_size, 'stderr':os.fstat(errors.fileno()).st_size}
            output.seek(0);errors.seek(0)
            stdout=output.read(1024*1024);stderr=errors.read(1024*1024)
    result={'executed':True,'syntax_valid':True,'python':sys.executable,'path':str(path),'sha256':digest,
            'returncode':process.returncode,'stdout':stdout[:65536].decode('utf-8','replace'),
            'stderr':stderr[:65536].decode('utf-8','replace'),'truncated':len(stdout)>65536 or len(stderr)>65536,
            'elapsed_s':round(time.monotonic()-started,3),'stop_reason':reason,
            'task_success':'not_evaluated'}
    # Text sidecars let the model page long output without rerunning the program
    # or repeatedly reading a single JSON-escaped stdout line.
    for channel, raw in (('stdout', stdout), ('stderr', stderr)):
        output_path = folder/(identifier+'.'+channel+'.txt')
        with os.fdopen(os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
            stream.write(raw.decode('utf-8', 'replace'))
        result[channel+'_path'] = str(output_path)
        result[channel+'_file_truncated'] = output_sizes[channel] > len(raw)
    report=folder/(identifier+'.json')
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2));report.chmod(0o600)
    store=EventStore(folder/'evidence.sqlite')
    try:
        store.append('episode',record(Episode(identifier,1,'python-execution','host',
            actions=[{'tool':'run_python','path':str(path),'sha256':digest}],observations=[{'report':str(report)}])))
        review=Review('pass' if result['returncode']==0 and reason is None else 'inconclusive',
                      1. if result['returncode']==0 and reason is None else 0.,
                      'Process exit evidence only; exit zero does not prove the user goal or physical success')
        store.append('review',record(review))
    finally:store.close()
    return {**result,'report':str(report),'review':record(review)}
