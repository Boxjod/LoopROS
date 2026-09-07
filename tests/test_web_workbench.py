import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError


class WebsiteWorkbenchTests(unittest.TestCase):
    def test_real_http_physics_camera_and_permission_boundaries(self):
        import os
        os.environ.setdefault('MUJOCO_GL','egl')
        from terminal.web_workbench import WorkbenchServer
        with tempfile.TemporaryDirectory() as d:
            server=WorkbenchServer(('127.0.0.1',0),d)
            def serve():
                try: server.serve_forever(poll_interval=.05)
                finally: server.server_close()  # Destroy render contexts on their owner thread.
            thread=threading.Thread(target=serve);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            def request(path,body=None,headers=None):
                req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                            headers={'Content-Type':'application/json',**(headers or {})})
                try:
                    with build_opener(ProxyHandler({})).open(req,timeout=20) as res: return res.status,res.read()
                except HTTPError as exc: return exc.code,exc.read()
            try:
                status,data=request('/api/session');self.assertEqual(status,200)
                token=json.loads(data)['token'];headers={'X-Loop-Token':token}
                self.assertEqual(request('/api/session',headers={'Origin':'https://untrusted.example'})[0],403)
                self.assertEqual(request('/api/session',headers={'Host':'untrusted.example'})[0],403)
                self.assertEqual(request('/artifacts/../../permissions.sqlite')[0],403)
                self.assertEqual(request('/api/tool',{'name':'sim_create','args':{'backend':'mujoco'}})[0],403)
                def call(name,args):
                    status,data=request('/api/tool',{'name':name,'args':args},headers)
                    return status,json.loads(data)
                server.gate.set_mode('plan')
                self.assertEqual(call('sim_create',{'backend':'mujoco'})[0],403)
                server.gate.set_mode('sim')
                status,data=call('sim_create',{'backend':'mujoco'});self.assertEqual(status,200,data)
                i=data['result']['instance']
                status,data=call('sim_edit',{'instance':i,'operation':'box','config':{'name':'cube','mass':.1,'position':[0,0,1]}})
                self.assertEqual(status,200,data)
                state=json.loads(request('/api/state')[1])['instances'][0]
                self.assertEqual(state['layout']['kind'],'geometry');self.assertEqual(state['layout']['items'][0]['name'],'cube')
                self.assertEqual(call('sim_camera',{'instance':i,'config':{'name':'head','position':[0,0,3],'quaternion':[1,0,0,0],'width':64,'height':48}})[0],200)
                status,data=call('sim_capture',{'instance':i,'cameras':['head']});self.assertEqual(status,200,data)
                url=data['result']['cameras']['head']['rgb'];self.assertTrue(url.startswith('/artifacts/'))
                self.assertTrue(request(url)[1].startswith(b'\x89PNG'))
                server.gate.set_rule('sim_step','ask')
                status,data=call('sim_step',{'instance':i,'action':[],'steps':10});self.assertEqual(status,403)
                rid=next(iter(data['requests']))
                self.assertEqual(json.loads(request('/api/state')[1])['instances'][0]['time'],0)
                self.assertEqual(request('/api/approve',{'id':rid,'allow':True})[0],403)
                self.assertEqual(request('/api/approve',{'id':rid,'allow':True},headers)[0],200)
                self.assertGreater(json.loads(request('/api/state')[1])['instances'][0]['time'],0)
                self.assertEqual(call('run_python',{'code':'print(1)'})[0],400)
                self.assertEqual(request('/api/approve',{'id':rid,'allow':True},headers)[0],400)
                self.assertEqual(call('sim_task',{'instance':i,'task':{'name':'passive','success':[{'kind':'exists','body':'cube'}]}})[0],200)
                status,data=call('sim_record',{'instance':i,'actions':[[]],'cameras':['head'],'steps':1})
                self.assertEqual(status,403)
                rid=next(iter(data['requests']))
                status,data=request('/api/approve',{'id':rid,'allow':True},headers)
                self.assertEqual(status,200,data)
                result=json.loads(data)['result']
                import io,h5py
                with h5py.File(io.BytesIO(request(result['path'])[1])) as f:
                    self.assertEqual(f['action'].shape,(1,0))
                    self.assertTrue(f.attrs['complete'])
                self.assertEqual(call('sim_close',{'instance':i})[0],200)
            finally: server.shutdown();thread.join(timeout=20)
