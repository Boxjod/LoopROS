"""Run with Isaac's python.sh. Dedicated headless process; never touches another GUI."""
import argparse
import faulthandler
import queue
import socketserver
import threading
import time
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
import uuid


class RuntimeBridge:
    def __init__(self, token, factory):
        self.token,self.factory=token,factory
        self.engine,self.instance=None,None
        self.seen=set()

    def handle(self, request):
        if not isinstance(request,dict) or not isinstance(request.get('token'),str) or not hmac.compare_digest(request['token'],self.token):
            raise PermissionError('Authentication failed')
        rid=request.get('id')
        if not isinstance(rid,str) or len(rid)>64 or rid in self.seen: raise ValueError('Missing or duplicate request ID')
        if len(self.seen)>=100000: raise RuntimeError('Bridge request limit reached; restart only after closing instance')
        self.seen.add(rid)
        method=request.get('method');args=request.get('args')
        if not isinstance(args,dict): raise ValueError('args must be an object')
        if method=='create':
            if self.engine is not None: raise RuntimeError('Isaac stage already owned; close it before creating another')
            if set(args)-{'scene'}: raise ValueError('Unknown create fields')
            self.engine=self.factory(**args);self.instance=uuid.uuid4().hex
            return {'instance':self.instance}
        if self.engine is None or request.get('instance')!=self.instance: raise ValueError('Stale or unowned Isaac instance')
        if method not in ('inspect','edit','camera','reset','step','capture','convert','close'): raise ValueError('Unknown bridge operation')
        if method=='close':
            self.engine.close();self.engine=None;self.instance=None
            return {'closed':True}
        return getattr(self.engine,method)(**args)


class NetworkBridge:
    """Socket I/O runs in threads; USD/PhysX calls run only in poll's owner thread."""
    def __init__(self, bridge, port):
        from toolchain.sim_isaac_client import MAX_MESSAGE
        self.bridge=bridge
        self.pending=queue.Queue(maxsize=16)
        owner=self
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                rid=None
                try:
                    self.connection.settimeout(130)
                    data=self.rfile.readline(MAX_MESSAGE+1)
                    if len(data)>MAX_MESSAGE or not data.endswith(b'\n'): raise ValueError('Invalid request framing')
                    request=json.loads(data);rid=request.get('id')
                    token=request.get('token')
                    if not isinstance(token,str) or not hmac.compare_digest(token,bridge.token): raise PermissionError('Authentication failed')
                    reply=queue.Queue(maxsize=1)
                    owner.pending.put_nowait((request,reply,time.monotonic()+120))
                    response=reply.get(timeout=125)
                except Exception as exc:
                    response={'id':rid,'error':str(exc)[:1000] or 'Receipt timeout; outcome unknown'}
                payload=json.dumps(response,allow_nan=False).encode()+b'\n'
                if len(payload)>MAX_MESSAGE: payload=json.dumps({'id':rid,'error':'Capture exceeds transport limit; reduce cameras/resolution'}).encode()+b'\n'
                try: self.wfile.write(payload)
                except OSError: pass
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads=True
        self.server=Server(('127.0.0.1',port),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def poll(self, timeout=.01):
        from toolchain.sim_isaac_client import encode
        try: request,reply,deadline=self.pending.get(timeout=timeout)
        except queue.Empty: return
        try:
            if time.monotonic()>deadline: raise TimeoutError('Request expired without execution')
            response={'id':request['id'],'result':encode(self.bridge.handle(request))}
        except Exception as exc:
            response={'id':request.get('id'),'error':str(exc)[:1000]}
        reply.put_nowait(response)

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Loop Isaac headless bridge (run with Isaac python.sh)')
    parser.add_argument('--config',type=Path,required=True,help='Write a new private connection file; never overwrite')
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--diagnostics',action='store_true',help='Dump Python stack if startup or a request exceeds 45 seconds')
    args=parser.parse_args(argv)
    if args.config.exists(): parser.error('Config exists; select a new file to avoid changing an existing endpoint')
    # Headless Kit must not attach to the desktop X session. On 4.5, an empty
    # startup stage can wait indefinitely for a viewport handle; the adapter
    # creates its owned stage after startup instead.
    os.environ.pop('DISPLAY',None)
    os.environ.pop('XAUTHORITY',None)
    from isaacsim import SimulationApp
    if args.diagnostics: faulthandler.dump_traceback_later(45,repeat=True)
    app=SimulationApp({'headless':True,'width':640,'height':480,'create_new_stage':False,'sync_loads':False,'multi_gpu':False,
        'extra_args':['--/plugins/carb.tasking.plugin/threadCount=8','--/plugins/omni.tbb.globalcontrol/maxThreadCount=8']})
    from toolchain.sim_isaac import IsaacSimulation
    import signal
    def stop(signum, frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    token=secrets.token_urlsafe(32)
    bridge=RuntimeBridge(token,lambda scene=None:IsaacSimulation(app,scene))
    network=NetworkBridge(bridge,args.port)
    try:
        port=network.server.server_address[1]
        args.config.parent.mkdir(parents=True,exist_ok=True)
        with os.fdopen(os.open(args.config,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:
            json.dump({'host':'127.0.0.1','port':port,'token':token},f)
        print('Loop Isaac bridge ready; connection file: '+str(args.config),flush=True)
        while app.is_running():
            network.poll()
    except KeyboardInterrupt: pass
    finally:
        if args.diagnostics: faulthandler.cancel_dump_traceback_later()
        network.close()
        if bridge.engine: bridge.engine.close()
        if args.config.exists():
            try:
                if json.loads(args.config.read_text()).get('token') == token: args.config.unlink()
            except (OSError, ValueError): pass
        app.close()


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    main()
