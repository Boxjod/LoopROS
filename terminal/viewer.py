"""Fixed-command MuJoCo installation and owned graphical viewer lifecycle."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from loop_robot.terminal.platform_support import venv_python


class ExistingViewer:
    """Reconnect only to an exact project-owned Linux worker, never a bare PID."""
    def __init__(self, pid, argv, started):
        self.pid,self.argv,self.started=pid,argv,started

    def poll(self):
        try:
            proc=Path('/proc')/str(self.pid)
            if proc.joinpath('cmdline').read_bytes().split(b'\0')[:-1] != [x.encode() for x in self.argv]: return 0
            if proc.joinpath('stat').read_text().rsplit(')',1)[1].split()[19] != self.started: return 0
            return None
        except OSError: return 0

    def terminate(self):
        import signal
        if self.poll() is None: os.kill(self.pid,signal.SIGTERM)

    def kill(self):
        import signal
        if self.poll() is None: os.kill(self.pid,signal.SIGKILL)

    def wait(self, timeout=5):
        deadline=time.monotonic()+timeout
        while self.poll() is None:
            if time.monotonic()>deadline: raise subprocess.TimeoutExpired(self.argv,timeout)
            time.sleep(.05)
        return 0


class SimulatorViewer:
    def __init__(self, root, directory):
        self.root, self.directory = Path(root), Path(directory)
        self.process = None
        self.scene = None
        self.ready = None
        self.lock = threading.RLock()
        self.adopt()

    def adopt(self):
        if not sys.platform.startswith("linux"): return
        owner=self.directory/"owner.json"
        try:
            data=json.loads(owner.read_text())
            argv=data["argv"]
            if len(argv)!=4 or Path(argv[1]).resolve()!= (self.root/"toolchain/viewer_worker.py").resolve(): return
            if not Path(argv[3]).resolve().is_relative_to(self.directory.resolve()): return
            process=ExistingViewer(data["pid"],argv,data["started"])
            if process.poll() is None:
                self.process=process;self.scene=Path(argv[2]);self.ready=Path(argv[3])
        except (OSError,ValueError,KeyError,TypeError): pass

    def python(self):
        local = venv_python(self.root / '.venv')
        if local.exists():
            return str(local)
        if sys.prefix != sys.base_prefix:
            return sys.executable
        local = venv_python(self.directory / 'runtime')
        if not local.exists():
            subprocess.run([sys.executable, '-m', 'venv', str(local.parents[1])], check=True, timeout=120, capture_output=True)
        return str(local)

    def ensure_installed(self):
        python = self.python()
        probe = [python, '-c', 'import mujoco, mujoco.viewer; print(mujoco.__version__)']
        result = subprocess.run(probe, capture_output=True, text=True, timeout=30)
        installed = False
        if result.returncode:
            result = subprocess.run([python, '-m', 'pip', 'install', 'mujoco>=3.3,<4', 'numpy>=1.26'],
                                    capture_output=True, text=True, timeout=240)
            if result.returncode:
                raise RuntimeError('MuJoCo installation failed in the managed environment; check pip connectivity')
            result = subprocess.run(probe, capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError('MuJoCo still cannot be imported after installation')
            installed = True
        return python, result.stdout.strip(), installed

    def status(self):
        running = self.process is not None and self.process.poll() is None
        ready = {}
        if self.ready and self.ready.exists():
            try:
                ready = json.loads(self.ready.read_text())
            except (OSError, ValueError):
                pass
        if not isinstance(ready, dict):
            ready = {}
        heartbeat = ready.get('heartbeat')
        fresh = (type(heartbeat) in (int, float) and 0 <= time.monotonic() - heartbeat < 3)
        return {**{key: ready.get(key) for key in ('motion', 'paused', 'speed', 'simulation_time', 'qpos', 'qvel', 'ctrl', 'contacts', 'actuators', 'last_command', 'joints', 'body_poses', 'mouse_selection')}, 'running': running, 'window_open': running and fresh and ready.get('window_open') is True,
                'status': ('open' if ready.get('window_open') is True else 'closed') if running and fresh else ('unresponsive' if running else 'closed'),
                'heartbeat_fresh': fresh, 'error': ready.get('error'),
                'scene_sha256': ready.get('scene_sha256'), 'model_bodies': ready.get('model_bodies', []),
                'model_geoms': ready.get('model_geoms', []),
                'pid': self.process.pid if running else None, 'scene': str(self.scene) if self.scene else None}

    def open(self, scene, force=False):
        from loop_robot.core.store import EventStore
        from loop_robot.core.contracts import Episode, Review, record
        self.directory.mkdir(parents=True,exist_ok=True)
        store=EventStore(self.directory/'control.sqlite')
        before=self.status()
        episode=Episode(uuid.uuid4().hex,1,'mujoco-viewer',before.get('scene_sha256') or 'unloaded',
                        observations=[before],actions=[{'action':'reload' if force else 'open','scene':str(scene)}])
        store.append('episode_started',record(episode))
        try:
            result=self._open(scene,force)
            episode.observations.append(result)
            episode.error=result.get('error')
            review=Review('pass' if result.get('window_open') else 'inconclusive',
                          1.0 if result.get('window_open') else 0.0,
                          'Fresh window heartbeat and content hash verified; physical task success not evaluated' if result.get('window_open') else str(result.get('error','Window unconfirmed')))
            store.append('episode',record(episode));store.append('review',record(review))
            return {**result,'review':record(review),'evidence_path':str(self.directory/'control.sqlite')}
        except Exception as exc:
            episode.error=str(exc);store.append('episode',record(episode));store.append('review',record(Review('inconclusive',0,'Viewer operation interrupted')))
            raise
        finally: store.close()

    def _open(self, scene, force=False):
        with self.lock:
            try:
                from loop_robot.toolchain.model_assets import snapshot
                _, _, digest = snapshot(scene)
            except OSError:
                digest = None
            current = self.status()
            if not force and current['window_open'] and self.scene == Path(scene) and digest is not None and current['scene_sha256'] == digest:
                return {**current, 'reloaded': False, 'reused_existing_window': True}
            python, version, installed = self.ensure_installed()
            if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
                return {'window_open': False, 'error': 'No desktop DISPLAY available for the MuJoCo GLFW viewer',
                        'mujoco_version': version, 'installed_now': installed}
            if digest is None:
                return {'window_open': False, 'error': 'Scene file is unavailable'}
            self.close()
            self.directory.mkdir(parents=True, exist_ok=True)
            self.scene = Path(scene)
            self.ready = self.directory / (uuid.uuid4().hex + '.json')
            log = self.ready.with_suffix('.log')
            with log.open('w') as output:
                launcher = str(Path(python).with_name('mjpython')) if sys.platform == 'darwin' else python
                self.process = subprocess.Popen([launcher, str(self.root / 'toolchain/viewer_worker.py'),
                                                 str(self.scene), str(self.ready)],
                                                stdout=output, stderr=output, start_new_session=True)
            if sys.platform.startswith('linux'):
                proc=Path('/proc')/str(self.process.pid)
                owner={'pid':self.process.pid,'argv':proc.joinpath('cmdline').read_bytes().decode().rstrip('\0').split('\0'),
                       'started':proc.joinpath('stat').read_text().rsplit(')',1)[1].split()[19]}
                temp=self.directory/'owner.tmp';temp.write_text(json.dumps(owner));temp.replace(self.directory/'owner.json')
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                state = self.status()
                if state['window_open'] and state['scene_sha256'] == digest:
                    return {**state, 'reloaded': True, 'reused_existing_window': False, 'mujoco_version': version, 'installed_now': installed, 'log': str(log)}
                if not state['running'] or self.ready.exists():
                    break
                time.sleep(.05)
            self.close()
            return {'window_open': False, 'error': 'Viewer failed to create a window; inspect the log', 'log': str(log)}

    def command(self, **args):
        from loop_robot.core.store import EventStore
        from loop_robot.core.contracts import Episode, Review, record
        from loop_robot.toolchain.viewer_control import validate
        validate(args)
        with self.lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / 'control.sqlite'
            store = EventStore(path)
            before = self.status()
            episode = Episode(uuid.uuid4().hex, 1, 'mujoco-viewer', before.get('scene_sha256') or 'unloaded',
                              observations=[before], actions=[args])
            store.append('episode_started', record(episode))
            try:
                result = self._command(**args)
                episode.observations.append(result)
                episode.error = result.get('error')
                verdict = 'pass' if result.get('executed') is True else ('fail' if result.get('executed') is False else 'inconclusive')
                review = Review(verdict, 1.0 if verdict == 'pass' else 0.0,
                                'Viewer acknowledged control application; task success not evaluated' if verdict == 'pass' else result.get('error', 'No evidence'))
                store.append('episode', record(episode))
                store.append('review', record(review))
                return {**result, 'review': record(review), 'evidence_path': str(path)}
            except Exception as exc:
                episode.error = str(exc)
                store.append('episode', record(episode))
                store.append('review', record(Review('inconclusive', 0, 'Control interrupted; inspect fresh state before retrying')))
                raise
            finally:
                store.close()

    def _command(self, **args):
        from loop_robot.toolchain.viewer_control import validate
        validate(args)
        with self.lock:
            if not self.status()['window_open']:
                return {'executed': False, 'error': 'Simulator window is not open or heartbeat is stale'}
            identity = uuid.uuid4().hex
            inbox = self.ready.with_suffix('.command.json')
            temporary = inbox.with_suffix('.tmp')
            temporary.write_text(json.dumps({'id': identity, 'expires': time.monotonic() + 3, 'args': args}))
            temporary.replace(inbox)
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                state = self.status()
                result = state.get('last_command')
                if result and result.get('id') == identity:
                    return {**result, 'window_open': state['window_open'], 'scene_sha256': state['scene_sha256']}
                if not state['running']:
                    break
                time.sleep(.02)
            inbox.unlink(missing_ok=True)
            # A timed-out command may have executed; never automatically retry motion.
            return {'id': identity, 'executed': None, 'error': 'No execution acknowledgement', 'review': {'verdict': 'inconclusive'}}

    def close(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
