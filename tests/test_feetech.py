import os
import pty
import select
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from toolchain.feetech import Bus, PositionLimits, packet, scan
from terminal.app import App
from model_fixture import call
from terminal.config import load_config

class FakeSerial:
    def __init__(self, model=777, echo=False, corrupt=False, drop_write=False):
        self.model,self.echo,self.corrupt,self.drop_write=model,echo,corrupt,drop_write
        self.data=bytearray();self.sent=[];self.closed=False
    def reset_input_buffer(self):self.data.clear()
    def close(self):self.closed=True
    def read(self,size):
        out=bytes(self.data[:size]);del self.data[:size];return out
    def write(self,raw):
        self.sent.append(raw);data=b''
        if raw[4]==2:
            data={3:self.model.to_bytes(2,'little'),33:b'\x00',40:b'\x01',56:b'\x00\x08\x00\x00\x00\x00\x78\x20'}[raw[5]]
        body=bytes((raw[2],len(data)+2,0))+data
        reply=b'\xff\xff'+body+bytes((~sum(body)&255,))
        if self.corrupt:reply=reply[:-1]+bytes((reply[-1]^1,))
        self.data.extend((raw if self.echo else b'')+(b'' if raw[4]==3 and self.drop_write else reply))
        return len(raw)

class FeetechTests(unittest.TestCase):
    def test_state_echo_model_and_corruption(self):
        self.assertEqual(packet(1,1).hex(),'ffff010201fb')
        io=FakeSerial(echo=True)
        with Bus('/test',transport=io) as bus:
            state=bus.read_state(1)
            self.assertEqual(state['position_ticks'],2048)
            self.assertEqual(state['voltage_V'],12.)
        self.assertTrue(io.closed)
        self.assertTrue(all(p[4] in (1,2) for p in io.sent))
        io=FakeSerial(model=123)
        with Bus('/test',transport=io) as bus:self.assertFalse(bus.read_state(1)['state_read'])
        self.assertEqual(len(io.sent),2)
        with Bus('/test',timeout=.005,transport=FakeSerial(corrupt=True)) as bus:
            with self.assertRaises(TimeoutError):bus.ping(1)
        with self.assertRaises(ValueError):packet(254,1)

    def test_control_limits_ambiguous_write_no_replay(self):
        io=FakeSerial(drop_write=True)
        with Bus('/test',timeout=.005,transport=io) as bus:
            limits=PositionLimits(1900,2200,30,100)
            with self.assertRaises(ValueError):bus.move_position(1,2100,20,limits=limits,request_id='bad')
            self.assertFalse(any(p[4]==3 for p in io.sent))
            with self.assertRaises(TimeoutError):bus.move_position(1,2050,20,limits=limits,request_id='one')
            before=len(io.sent)
            self.assertTrue(bus.move_position(1,2050,20,limits=limits,request_id='one')['duplicate'])
            self.assertEqual(len(io.sent),before)
            with self.assertRaises(ValueError):bus.move_position(1,2051,20,limits=limits,request_id='one')

    def test_scan_cancel(self):
        factory=lambda port,baud:Bus(port,baud,transport=FakeSerial())
        self.assertEqual(len(scan('/test',[1,2],[1000000],bus_factory=factory)['motors']),2)
        event=threading.Event();event.set()
        r=scan('/test',[1],[1000000],stop_event=event,bus_factory=factory)
        self.assertFalse(r['scan_complete']);self.assertEqual(r['attempts'],0)

    def test_real_pyserial_pty(self):
        master,slave=pty.openpty();port=os.ttyname(slave);stop=threading.Event()
        def servo():
            buffer=bytearray();fake=FakeSerial(echo=True)
            while not stop.is_set():
                if not select.select([master],[],[],.05)[0]:continue
                buffer.extend(os.read(master,128))
                while len(buffer)>=4 and len(buffer)>=buffer[3]+4:
                    size=buffer[3]+4;raw=bytes(buffer[:size]);del buffer[:size]
                    fake.write(raw);os.write(master,fake.read(128))
        thread=threading.Thread(target=servo);thread.start()
        try:
            with Bus(port,timeout=.1) as bus:self.assertEqual(bus.read_state(1)['model'],'sts3215')
        finally:stop.set();thread.join(1);os.close(master);os.close(slave)

    def test_terminal_reports_permissions_direct_scan(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                with patch('terminal.feetech.feetech.scan',return_value={'motors':[{'id':1,'baudrate':1000000,'model_number':777,'model':'sts3215'}],'scan_complete':True,'verdict':'pass'}):
                    self.assertTrue(Path(app.tool('feetech_scan',{'port':'/test'})['report']).exists())
                    real=app.tool
                    def dispatch(name,args):
                        return {'devices':[{'kind':'serial','node':'/test'}]} if name=='devices' else real(name,args)
                    app.agent.history=[{'role':'user','content':'是USB-TTL连接的飞特舵机'}]
                    with patch.object(app,'tool',side_effect=dispatch), patch.object(app.client,'complete',side_effect=[call('load_toolset',name='robotics'),call('devices'),call('feetech_scan',port='/test'),{'content':'1000000 baud'}, {'content':'请明确下一步操作。'}]):
                        self.assertIn('1000000 baud',app.dispatch('先检测舵机的波特率'))
                        self.assertIn('明确下一步',app.dispatch('你帮我执行'))
                app.permissions.set_mode('plan')
                with self.assertRaises(PermissionError):app.tool('feetech_scan',{'port':'/test'})
                self.assertTrue(app.tool('feetech_environment',{})['pyserial_available'])
            finally:app.close()


class ReferenceLoopTests(unittest.TestCase):
    def test_identical_web_fetch_is_not_executed_again(self):
        from terminal.llm import ChatAgent
        from types import SimpleNamespace
        import json
        call={'tool_calls':[{'id':'c','function':{'name':'web_fetch','arguments':'{"url":"https://pypi.org/project/pyserial/"}'}}]}
        replies=iter([call,call,{'content':'No Python execution evidence.'}])
        executed=[];events=[]
        agent=ChatAgent(SimpleNamespace(complete=lambda *a,**kw:next(replies)),[],lambda *a:executed.append(a) or {'text':'package page'})
        agent.on_event=lambda kind,value:events.append((kind,value))
        agent.reply('execute Python')
        self.assertEqual(len(executed),1)
        self.assertTrue(any(kind=='result' and json.loads(value).get('repeated_request_skipped') for kind,value in events))
