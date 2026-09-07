"""Authenticated bounded local RPC client. No retry after an uncertain mutation."""
import base64
import io
import json
from pathlib import Path
import socket
import uuid

MAX_MESSAGE=64*1024*1024


def encode(value):
    import numpy as np
    if isinstance(value,np.ndarray):
        stream=io.BytesIO();np.save(stream,value,allow_pickle=False)
        return {'__npy__':base64.b64encode(stream.getvalue()).decode()}
    if isinstance(value,dict): return {str(k):encode(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [encode(v) for v in value]
    if isinstance(value,np.generic): return value.item()
    return value


def decode(value):
    if isinstance(value,dict) and set(value)=={'__npy__'}:
        import numpy as np
        return np.load(io.BytesIO(base64.b64decode(value['__npy__'],validate=True)),allow_pickle=False)
    if isinstance(value,dict): return {k:decode(v) for k,v in value.items()}
    if isinstance(value,list): return [decode(v) for v in value]
    return value


class IsaacSimulationClient:
    backend='isaac'

    def __init__(self, config, scene=None):
        if config is None or not Path(config).is_file():
            raise ValueError('Isaac bridge not configured; start loop-isaac-host with --config PATH')
        path=Path(config)
        if path.stat().st_mode & 0o077: raise ValueError('Isaac connection file must have mode 0600')
        self.config=json.loads(path.read_text())
        if self.config.get('host') not in ('127.0.0.1','::1','localhost') or not self.config.get('token'):
            raise ValueError('Use an authenticated localhost bridge (or an explicitly configured SSH tunnel)')
        self.instance=None
        result=self.request('create',{'scene':scene})
        self.instance=result['instance']

    def request(self,method,args):
        rid=uuid.uuid4().hex
        request={'id':rid,'token':self.config['token'],'instance':self.instance,'method':method,'args':args}
        payload=json.dumps(request,allow_nan=False).encode()+b'\n'
        if len(payload)>MAX_MESSAGE: raise ValueError('Request too large')
        try:
            with socket.create_connection((self.config['host'],self.config['port']),timeout=120) as conn:
                conn.settimeout(120);conn.sendall(payload)
                response=conn.makefile('rb').readline(MAX_MESSAGE+1)
        except (OSError,TimeoutError) as exc:
            raise RuntimeError('Isaac bridge receipt missing; outcome unknown, do not retry mutation automatically: '+str(exc)) from exc
        if len(response)>MAX_MESSAGE or not response.endswith(b'\n'): raise RuntimeError('Invalid/truncated bridge response; outcome unknown')
        result=json.loads(response)
        if result.get('id')!=rid: raise RuntimeError('Bridge response ID mismatch')
        if 'error' in result: raise RuntimeError(result['error'])
        return decode(result['result'])

    def inspect(self): return self.request('inspect',{})
    def edit(self,operation,config): return self.request('edit',{'operation':operation,'config':config})
    def camera(self,config): return self.request('camera',{'config':config})
    def convert(self,source,format,output): return self.request('convert',{'source':source,'format':format,'output':output})
    def reset(self,seed=0): return self.request('reset',{'seed':seed})
    def step(self,action,steps=1): return self.request('step',{'action':action,'steps':steps})
    def capture(self,names): return self.request('capture',{'names':names})
    def close(self):
        if self.instance is not None:
            self.request('close',{});self.instance=None
