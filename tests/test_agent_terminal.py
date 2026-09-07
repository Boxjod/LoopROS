import codecs
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
try:
    import pyte
except ImportError:
    pyte=None


@unittest.skipUnless(pyte,'pyte required')
class AgentTerminalTests(unittest.TestCase):
    def test_select_send_receipts_and_chinese_stream(self):
        with tempfile.TemporaryDirectory() as folder:
            master,slave=pty.openpty()
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',36,110,0,0))
            screen=pyte.HistoryScreen(110,36,history=5000)
            screen.write_process_input=lambda s:os.write(master,s.encode())
            stream=pyte.Stream(screen);decoder=codecs.getincrementaldecoder('utf-8')()
            process=subprocess.Popen([sys.executable,str(Path(__file__).parent/'fixtures/slash_terminal.py'),folder],
                stdin=slave,stdout=slave,stderr=slave,env=dict(os.environ,TERM='xterm-256color',
                LOOP_HOME=folder+'/home',LOOP_TASK_AUTOSTART='0',LOOP_AGENT_UI_FIXTURE='1'))
            os.close(slave)
            raw=bytearray()
            def pump(seconds=.4):
                deadline=time.monotonic()+seconds
                while time.monotonic()<deadline:
                    if select.select([master],[],[],.02)[0]:
                        try:data=os.read(master,65536)
                        except OSError:break
                        raw.extend(data);stream.feed(decoder.decode(data))
                return '\n'.join(screen.display)
            def send(text,seconds=.4):
                os.write(master,(text+'\r').encode());return pump(seconds)
            try:
                pump(.8)
                self.assertIn('Reader',send('/spawn'))
                shown=send('Reader')
                self.assertIn('/spawn Reader',shown)
                self.assertNotIn('Unknown role',shown)
                send('检查上下文',.7)
                shown=send('/agents')
                self.assertIn('检查上下文',shown);self.assertIn('@1',shown)
                send('/send')
                os.write(master,b'\r');shown=pump(.3)
                self.assertIn('/send @1',shown)
                send('保持中文输出',1)
                shown=send('/agent-messages @1',.5)
                self.assertIn('delivered',shown)
                self.assertIn('保持中文输出',shown)
                shown=send('/result @1')
                self.assertIn('Agent returned',shown)
                send('中',.15)
                os.write(master,'文2'.encode())
                self.assertIn('文2',pump(.35))
                pump(.6);os.write(master,b'\r');pump(1)
                send('/exit')
                self.assertEqual(process.wait(timeout=5),0)
                self.assertEqual([json.loads(s) for s in (Path(folder)/'inputs.jsonl').read_text().splitlines()],['中','文2'])
                self.assertNotIn(b'Traceback',raw)
                self.assertNotIn(b'Master error',raw)
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=5)
                os.close(master)
