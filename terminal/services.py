"""Own inference-only foreground processes; no legacy robot-control scripts."""
import os
from pathlib import Path
import signal
import subprocess


class PolicyServices:
    def __init__(self, config, logs, resources=None):
        self.config, self.logs, self.processes = config, Path(logs), {}
        self.resources, self.leases = resources, {}

    def status(self):
        for name, token in list(self.leases.items()):
            if self.processes[name].poll() is not None:
                self.resources.release(token)
                del self.leases[name]
        return {name: ("RUNNING" if name in self.processes and self.processes[name].poll() is None
                       else "STOPPED" if spec["argv"] else "NOT_CONFIGURED")
                for name, spec in self.config.items()}

    def start(self, name):
        spec = self.config[name]
        argv = spec["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise ValueError("请先配置 {} 的 inference-only 前台服务 argv".format(name))
        if self.status()[name] == "RUNNING":
            return self.status()
        if self.resources is None and any(state == "RUNNING" for other, state in self.status().items() if other != name):
            raise RuntimeError("默认只驻留一个策略服务；先停止另一个，避免显存争用")
        self.logs.mkdir(parents=True, exist_ok=True)
        # Do not pass the chat provider key to local policy processes.
        env = {k: v for k, v in os.environ.items() if not k.endswith(("API_KEY", "TOKEN", "SECRET"))}
        token = None
        if self.resources is not None:
            from loop_robot.core.resources import ResourceBusy
            token = self.resources.inspect(acquire=True, workload='policy_service', request=spec.get('resources', {}))
            if token is None:
                raise ResourceBusy('Waiting for resources: ' + self.resources.last['reason'])
        try:
            with (self.logs / (name + ".log")).open("ab") as log:
                self.processes[name] = subprocess.Popen(argv, cwd=spec.get("cwd") or None,
                                                        env=env, stdout=log, stderr=log,
                                                        start_new_session=os.name != "nt",
                                                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            if token:
                self.leases[name] = token
                self.resources.bind(token, self.processes[name].pid)
        except BaseException:
            if name in self.processes: self.stop(name)
            if token: self.resources.release(token)
            raise
        return self.status()  # RUNNING is not inference readiness.

    def stop(self, name):
        if name not in self.config:
            raise ValueError("unknown model")
        process = self.processes.get(name)
        if process is not None and process.poll() is None:
            if os.name == "nt":
                # Only the tree belonging to a process created by this instance.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               check=True, capture_output=True, timeout=10)
                process.wait(timeout=5)
                return self.status()
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        return self.status()

    def close(self):
        for name in self.config:
            self.stop(name)
