"""Actual PTY: Chinese streaming, pasted chips, images, deletion and resize."""
import base64
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
import pyte


class ComposerRenderTests(unittest.TestCase):
    def test_chips_during_chinese_stream_and_image_deletion(self):
        with tempfile.TemporaryDirectory() as d:
            image=Path(d)/'sample.png'
            image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jS1cAAAAASUVORK5CYII='))
            master,slave=pty.openpty()
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
            screen=pyte.HistoryScreen(100,24,history=2000)
            screen.write_process_input=lambda s:os.write(master,s.encode())
            parser=pyte.Stream(screen);decoder=codecs.getincrementaldecoder('utf8')()
            process=subprocess.Popen([sys.executable,'tests/fixtures/stream_terminal.py',d+'/state'],
                cwd=Path(__file__).resolve().parents[1],stdin=slave,stdout=slave,stderr=slave,
                env=dict(os.environ,TERM='xterm-256color',LOOP_HOME=d+'/home'))
            os.close(slave)
            def drain(duration=.35):
                deadline=time.monotonic()+duration
                while time.monotonic()<deadline:
                    if select.select([master],[],[],.02)[0]:
                        try:chunk=os.read(master,65536)
                        except OSError:return
                        parser.feed(decoder.decode(chunk))
            def shown():return '\n'.join(screen.display)
            evidence={}
            try:
                drain(.7);os.write(master,'你好\r'.encode());drain(.15)
                os.write(master,('说明 '+'\x1b[200~'+'\n'.join('print("中文代码%d")'%i for i in range(20))+'\x1b[201~').encode())
                drain(.4)
                self.assertIn('[Paste #1 · 20 lines]',shown())
                self.assertNotIn('中文代码19',shown());evidence['stream_and_paste']=screen.display[:]
                os.write(master,b'\x7f');drain(.2);self.assertIn('[Paste #1',shown())
                os.write(master,b'\x7f');drain(.2);self.assertNotIn('[Paste #1',shown());self.assertIn('说明',shown())
                os.write(master,b'\x03');drain(1.2)
                os.write(master,('/attach '+str(image)+' '+str(image)+'\r').encode());drain(.6)
                self.assertIn('[Image #2]',shown());self.assertIn('[Image #3]',shown())
                evidence['images']=screen.display[:]
                os.write(master,b'\x7f');drain(.2);self.assertIn('[Image #3]',shown())
                os.write(master,b'\x7f');drain(.2);self.assertNotIn('[Image #3]',shown());self.assertIn('[Image #2]',shown())
                fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',12,40,0,0));screen.resize(lines=12,columns=40)
                import signal
                process.send_signal(signal.SIGWINCH);drain(.5)
                self.assertIn('[Image #2]',shown());evidence['narrow']=screen.display[:]
                os.write(master,b'\x04');drain(.5);self.assertEqual(process.wait(timeout=5),0)
                import sqlite3
                with sqlite3.connect(d+'/state/conversation.sqlite') as db:
                    saved=json.loads(db.execute('select data from checkpoint where id=1').fetchone()[0])
                self.assertEqual(len(saved['attachments']),1)
                self.assertTrue(saved['composer']['blocks'])
                # Restart fresh, then explicitly restore the saved chip + media payload.
                os.close(master)
                master,slave=pty.openpty()
                fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',12,40,0,0))
                process=subprocess.Popen([sys.executable,'tests/fixtures/stream_terminal.py',d+'/state'],
                    cwd=Path(__file__).resolve().parents[1],stdin=slave,stdout=slave,stderr=slave,
                    env=dict(os.environ,TERM='xterm-256color',LOOP_HOME=d+'/home'))
                os.close(slave);screen.reset();drain(.8)
                self.assertNotIn('[Image #2]',shown())
                os.write(master, ('/resume '+saved['session_id']).encode());drain(.3)
                os.write(master, b'\r');drain(.8)
                self.assertIn('[Image #2]',shown());evidence['restored']=screen.display[:]
                os.write(master,b'\x03/exit\r');drain(.5);self.assertEqual(process.wait(timeout=5),0)
                output=Path(__file__).resolve().parents[1]/'artifacts/composer-chips'
                output.mkdir(parents=True,exist_ok=True)
                (output/'pty-screens.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
            finally:
                if process.poll() is None:process.kill()
                process.wait(timeout=5);os.close(master)
