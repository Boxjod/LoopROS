"""Explicit subprocess bridge; never imports or modifies the upstream repo."""
import os
from pathlib import Path
import subprocess


def template_command(repo, python, segments, output):
    repo, segments, output = (Path(x).resolve() for x in (repo, segments, output))
    if not (repo / "src/ego2mujoco/cli.py").is_file() or not segments.is_file():
        raise ValueError("missing Ego2MuJoCo source or task segments")
    if output.exists():
        raise ValueError("use a new output directory; no implicit overwrite")
    return [str(Path(python).resolve()), "-m", "ego2mujoco.cli", "run-template-mujoco",
            str(segments), "--run-dir", str(output)]


def run_template(repo, python, segments, output, timeout_s=300):
    command = template_command(repo, python, segments, output)
    if timeout_s <= 0:
        raise ValueError("positive timeout required")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(repo).resolve() / "src")
    # CLI output is inherited, avoiding an unbounded in-memory video/log buffer.
    return subprocess.run(command, cwd=str(Path(repo).resolve()), env=env,
                          check=True, timeout=timeout_s)
