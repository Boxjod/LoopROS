"""Owned background supervisor process. Commands and receipts live in tasks.sqlite."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from core.tasks import TaskStore
from terminal.task_supervisor import load_policy


def policy_path(state):
    from terminal.config import user_config_file
    local=Path(state)/'task_runtime.json'
    return local if local.exists() else user_config_file('task_runtime.json')


def status(state):
    store=TaskStore(Path(state)/'tasks.sqlite');owner=store.meta('owner') or {}
    alive=False
    if owner.get('pid'):
        try:
            if sys.platform.startswith('linux'):
                path=Path('/proc')/str(owner['pid'])
                alive=path.joinpath('cmdline').read_bytes().split(b'\0')[:-1]==[a.encode() for a in owner['argv']] and path.joinpath('stat').read_text().rsplit(')',1)[1].split()[19]==owner['started']
            else:
                os.kill(owner['pid'],0);alive=True
        except (OSError,KeyError): pass
    heartbeat=store.meta('heartbeat') or 0
    return {'process_alive':alive,'heartbeat_fresh':alive and time.time()-heartbeat<5,
            'pid':owner.get('pid'),'config':str(policy_path(state)), 'database':str(store.path),
            'stop_requested':bool(store.meta('stop_requested'))}


def start(app):
    from terminal.app import TOOLS
    app.permissions.check('spawn_agent',{'role':'TaskSupervisor'})
    config=load_policy(policy_path(app.state_dir),{t['function']['name'] for t in TOOLS})
    if os.environ.get("LOOP_TASK_AUTOSTART")=="0":
        return {**status(app.state_dir),"autostart_disabled":True}
    current=status(app.state_dir)
    if current['process_alive']: return current
    store=TaskStore(app.state_dir/'tasks.sqlite');store.meta('stop_requested',False)
    argv=[sys.executable,'-m','terminal.task_service','--state-dir',str(app.state_dir.resolve())]
    env=dict(os.environ)
    # Session-only credentials remain in the child environment, never argv/config/ledger.
    if app.client.key: env[app.client.config['api_key_env']]=app.client.key
    from terminal.config import ROOT
    with (app.state_dir/'task_service.log').open('ab') as log:
        subprocess.Popen(argv,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        result=status(app.state_dir)
        if result['heartbeat_fresh']: return result
        time.sleep(.05)
    return {**status(app.state_dir),'error':'Supervisor startup not confirmed; inspect task_service.log'}


def stop(state):
    store=TaskStore(Path(state)/'tasks.sqlite');store.meta('stop_requested',True)
    return {'stop_requested':True,'effect':'Stop subsequent work; does not roll back executed actions',**status(state)}


def main():
    import argparse
    from terminal.app import App, TOOLS, lock_terminal
    from terminal.config import load_config
    from terminal.task_supervisor import TaskSupervisor
    parser=argparse.ArgumentParser();parser.add_argument('--state-dir',type=Path,required=True);args=parser.parse_args()
    state=args.state_dir;state.mkdir(parents=True,exist_ok=True)
    with (state/'task_service.lock').open('a+b') as lock:
        try: lock_terminal(lock)
        except BlockingIOError: return
        config=load_policy(policy_path(state),{t['function']['name'] for t in TOOLS})
        app=App(load_config(),state,background=True)
        app.runtime.close()  # TaskSupervisor owns its own independent subprocess broker.
        store=TaskStore(state/'tasks.sqlite')
        argv=[sys.executable,'-m','terminal.task_service','--state-dir',str(state)]
        started=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19] if sys.platform.startswith('linux') else None
        store.meta('owner',{'pid':os.getpid(),'argv':argv,'started':started})
        done=threading.Event()
        def heartbeat():
            while not done.is_set():
                store.meta('heartbeat',time.time());done.wait(1)
        thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
        def dispatch(name,arguments):
            if name in ('generate_scene','compose_scene','load_model','open_simulator','simulator_status','simulator_control'):
                app.restore_scene_state()
            # The normal broker gate is still authoritative for every action.
            return app.tool(name,arguments)
        provider=[app.client.config['base_url'].rstrip('/'),app.client.config['model'],app.client.config.get('protocol','openai')]
        supervisor=TaskSupervisor(store,config,{'llm':app.client},TOOLS,dispatch,state/'task_agents.jsonl',provider,learning=app.learning,admission=app.resources)
        serial_paths=None
        def poll_os_events():
            nonlocal serial_paths
            enabled={t['event'] for t in config['triggers'] if t['enabled']}
            if not enabled.intersection({'serial.appeared','serial.disappeared'}): return
            directory=Path('/dev/serial/by-id')
            try: present={str(p) for p in directory.iterdir()}
            except FileNotFoundError: present=set()
            if serial_paths is not None:
                for path in present-serial_paths:
                    if 'serial.appeared' in enabled: store.signal('serial.appeared',{'device_path':path})
                for path in serial_paths-present:
                    if 'serial.disappeared' in enabled: store.signal('serial.disappeared',{'device_path':path})
            serial_paths=present
        try:
            while not store.meta('stop_requested'):
                poll_os_events()
                app.enforce_node_permissions(close_viewer=False)
                if app.permissions.snapshot()['mode']=='plan':
                    for agent in list(supervisor.running): supervisor.runtime.cancel(agent)
                    supervisor.poll(launch=False)
                elif not app.client.resolved_key():
                    for task in store.list():
                        if task['state'] in ('queued','retry_wait'):
                            store.update(task['id'],'waiting_input',{'reason':'Model credentials unavailable; configure the current provider and resume the task'})
                else:
                    supervisor.poll()
                time.sleep(.2)
        finally:
            supervisor.close();done.set();thread.join(timeout=2)
            store.meta('heartbeat',0)
            # Closing a task supervisor must not close a user's simulator window.
            app.nodes.close();app.scheduler.close();app.providers.close()


if __name__=='__main__':
    from release_runtime import runtime_session
    with runtime_session():
        main()
