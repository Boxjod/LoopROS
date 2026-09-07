"""Local website + simulation API. One owner thread for physics and EGL rendering."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATIC = {'index.html','zh-CN.html','install.html','style.css','site.js','favicon.png',
          'workbench.html','workbench.css','workbench.js','three.module.min.js','three.LICENSE.txt'}


def layout(engine):
    """Read render geometry; never infer contact or task success from the viewer."""
    state = engine.inspect()
    if engine.backend != 'mujoco':
        return {'kind':'bounds','items':[{'name':name,'type':'box',
            'position':[(a+b)/2 for a,b in zip(v['min'],v['max'])],
            'size':[b-a for a,b in zip(v['min'],v['max'])],
            'rotation':[1,0,0,0,1,0,0,0,1],'color':[.55,.65,.75,1]}
            for name,v in state['bounds'].items()]}
    m,d,mj=engine.model,engine.data,engine.mj
    items=[]
    for i in range(m.ngeom):
        kind=int(m.geom_type[i])
        if kind == int(mj.mjtGeom.mjGEOM_PLANE): continue
        body=int(m.geom_bodyid[i]);size=m.geom_size[i].tolist()
        item={'name':mj.mj_id2name(m,mj.mjtObj.mjOBJ_BODY,body) or 'world',
              'position':d.geom_xpos[i].tolist(),'rotation':d.geom_xmat[i].tolist(),
              'color':m.geom_rgba[i].tolist()}
        if kind==int(mj.mjtGeom.mjGEOM_MESH):
            mesh=int(m.geom_dataid[i]);start=int(m.mesh_vertadr[mesh]);n=int(m.mesh_vertnum[mesh])
            fs=int(m.mesh_faceadr[mesh]);fn=int(m.mesh_facenum[mesh])
            if n>100000 or fn>200000: continue
            item.update(type='mesh',vertices=m.mesh_vert[start:start+n].reshape(-1).tolist(),
                        indices=m.mesh_face[fs:fs+fn].reshape(-1).tolist())
        else:
            kinds={int(mj.mjtGeom.mjGEOM_BOX):'box',int(mj.mjtGeom.mjGEOM_SPHERE):'sphere',
                   int(mj.mjtGeom.mjGEOM_CAPSULE):'capsule',int(mj.mjtGeom.mjGEOM_CYLINDER):'cylinder',
                   int(mj.mjtGeom.mjGEOM_ELLIPSOID):'ellipsoid'}
            if kind not in kinds: continue
            item.update(type=kinds[kind],size=[x*2 for x in size] if kinds[kind]=='box' else size)
        items.append(item)
    return {'kind':'geometry','items':items,'appearance':'geometry and base colors; textures not transferred'}


class WorkbenchServer(HTTPServer):
    allow_reuse_address=True
    def __init__(self, address, directory, isaac_config=None):
        from terminal.permissions import PermissionGate
        from toolchain.simulation import SimulationWorkbench
        self.directory=Path(directory).resolve();self.directory.mkdir(parents=True,exist_ok=True)
        self.gate=PermissionGate(self.directory/'permissions.sqlite')
        self.service=SimulationWorkbench(self.directory/'web-simulation',isaac_config)
        self.token=secrets.token_urlsafe(32)
        super().__init__(address, Handler)

    def server_close(self):
        try: self.service.close()
        finally: super().server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # Do not log URLs, private paths or tokens.

    def reply(self, status, value):
        data=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
        self.send_bytes(status,data,'application/json; charset=utf-8')

    def send_bytes(self,status,data,content_type):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        try: self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError): pass

    def trusted(self, write=False):
        port=self.server.server_port
        hosts={'127.0.0.1:'+str(port),'localhost:'+str(port)}
        if self.headers.get('Host') not in hosts: raise PermissionError('Invalid local host')
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://'+h for h in hosts}: raise PermissionError('Cross-origin access denied')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site': raise PermissionError('Cross-site access denied')
        if write and not hmac.compare_digest(self.headers.get('X-Loop-Token',''),self.server.token):
            raise PermissionError('Reload the local workbench before executing actions')

    def do_GET(self):
        try:
            self.trusted()
            path=unquote(urlsplit(self.path).path)
            if path=='/api/session':
                return self.reply(200,{'token':self.server.token,'permissions':self.server.gate.snapshot(),
                    'example_scene':str(ROOT/'examples/simulation_workbench.xml')})
            if path=='/api/state':
                from terminal.simulation import call_service
                result=call_service(self.server.service,self.server.gate,'sim_list',{})
                for state in result['instances']:
                    state['layout']=layout(self.server.service.entry(state['instance'])['engine'])
                return self.reply(200,result)
            if path.startswith('/artifacts/'):
                base=(self.server.directory/'web-simulation').resolve()
                file=(base/path[len('/artifacts/'):]).resolve()
                if not file.is_relative_to(base) or file.suffix not in ('.png','.npz','.json','.hdf5'):
                    raise PermissionError('Artifact outside workbench')
            elif path in ('/logo.png','/assets/logo.png'):
                file=ROOT/'assets/logo.png'
            else:
                name='workbench.html' if path=='/' else path.removeprefix('/')
                if name not in STATIC: return self.reply(404,{'error':'Not found'})
                file=ROOT/'website'/name
            data=file.read_bytes()
            self.send_bytes(200,data,mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        except PermissionError as exc: self.reply(403,{'error':str(exc)})
        except FileNotFoundError: self.reply(404,{'error':'Not found'})
        except Exception as exc: self.reply(400,{'error':str(exc)})

    def public_result(self,value):
        # Only map files generated by this service; no arbitrary file serving.
        base=(self.server.directory/'web-simulation').resolve()
        if isinstance(value,dict): return {k:self.public_result(v) for k,v in value.items()}
        if isinstance(value,list): return [self.public_result(v) for v in value]
        if isinstance(value,str) and value.startswith(str(base)+'/'):
            return '/artifacts/'+str(Path(value).relative_to(base))
        return value

    def do_POST(self):
        try:
            self.trusted(write=True)
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=2*1024*1024: raise ValueError('Invalid request size')
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('JSON required')
            body=json.loads(self.rfile.read(length))
            from terminal.simulation import call_service
            path=urlsplit(self.path).path
            if path=='/api/tool':
                if not isinstance(body,dict) or set(body)!={'name','args'}: raise ValueError('Expected name and args')
                result=call_service(self.server.service,self.server.gate,body['name'],body['args'])
            elif path=='/api/approve':
                # Separate operator UI action; absent from model/MCP tool schema.
                if set(body)!={'id','allow'} or type(body['allow']) is not bool: raise ValueError('Invalid approval')
                if not body['allow']:
                    self.server.gate.reject(body['id']);result={'rejected':True}
                else:
                    result=self.server.gate.approve(body['id'],lambda n,a:call_service(self.server.service,self.server.gate,n,a))
            else: return self.reply(404,{'error':'Not found'})
            self.reply(200,{'result':self.public_result(result)})
        except PermissionError as exc:
            self.reply(403,{'error':str(exc),'requests':self.server.gate.requests()})
        except Exception as exc: self.reply(400,{'error':str(exc)})


def main(argv=None):
    import os
    from terminal.config import DEFAULT_STATE_DIR
    from terminal.home import loop_home
    parser=argparse.ArgumentParser(prog='loop web',description='Local Loop ROS visual simulation workbench')
    parser.add_argument('--port',type=int,default=8768)
    parser.add_argument('--state-dir',type=Path,default=DEFAULT_STATE_DIR)
    parser.add_argument('--isaac-config',type=Path,default=loop_home()/'isaac-bridge.json')
    args=parser.parse_args(argv)
    if os.name=='posix': os.environ.setdefault('MUJOCO_GL','egl')
    import signal
    def stop(signum,frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    server=WorkbenchServer(('127.0.0.1',args.port),args.state_dir,args.isaac_config)
    print('Loop workbench: http://127.0.0.1:'+str(server.server_port)+'/workbench.html',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__': main()
