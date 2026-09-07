"""Install into the project venv and expose non-overwriting user-level launchers."""
from pathlib import Path
import argparse
import os
import platform
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terminal.platform_support import venv_python


def windows_launcher(executable):
    path = str(executable).replace("%", "%%")
    return '@echo off\nrem Loop ROS managed launcher\nsetlocal DisableDelayedExpansion\nchcp 65001 >nul\n"{}" %*\n'.format(path)


def main():
    parser = argparse.ArgumentParser(description="Install Loop ROS — Loop Robot Operating System")
    parser.add_argument("--terminal-only", action="store_true", help="Skip local MuJoCo/NumPy installation")
    parser.add_argument("--check", action="store_true", help="Print environment and exit without installing")
    args = parser.parse_args()
    print("Loop ROS | {} {} | Python {} | {}".format(platform.system(), platform.release(), platform.python_version(), platform.machine()))
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10+ required. Use a compatible isolated Python or the documented SSH client route; do not replace system Python.")
    windows = os.name == "nt"
    if windows and tuple(sys.getwindowsversion()[:2]) < (6, 3):
        raise SystemExit("Native Windows 7/8 is not supported. Use SSH to a supported Loop ROS host.")
    if args.check:
        print("Interpreter prerequisites met; this does not certify hardware, graphics or binary dependencies.")
        return
    root = ROOT
    environment = root / ".venv"
    python = venv_python(environment)
    target_dir = Path.home() / ".local/bin"
    # Validate destinations before installing. Never overwrite another program.
    names = ("loop", "loop-switch", "looper", "looper-switch")
    def owned_link(link, name):
        if not link.is_symlink():
            return False
        return link.readlink() in (environment / "bin" / name,
                                  root.parent / "loop_robot" / ".venv/bin" / name,
                                  root.parent / "looper_M1" / ".venv/bin" / name)
    for name in names:
        link = target_dir / (name + ".cmd" if windows else name)
        expected = windows_launcher(python.parent / (name + '.exe'))
        if windows:
            if link.exists() and link.read_text(encoding="utf-8") != expected:
                raise SystemExit("Destination already exists; left unchanged: " + str(link))
        elif (link.exists() or link.is_symlink()) and not owned_link(link, name):
            raise SystemExit("Destination already exists; left unchanged: " + str(link))
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "-e", str(root) + ("" if args.terminal_only else "[sim]")], check=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        if windows:
            link = target_dir / (name + ".cmd")
            content = windows_launcher(python.parent / (name + '.exe'))
            if not link.exists():
                link.write_text(content, encoding="utf-8")
            continue
        link = target_dir / name
        if link.is_symlink() and link.readlink() != environment / "bin" / name:
            link.unlink()  # Only validated project-owned legacy launchers.
        if not link.is_symlink():
            link.symlink_to(environment / "bin" / name)
    if windows:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            try:
                old, kind = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                old, kind = "", winreg.REG_EXPAND_SZ
            if str(target_dir).casefold() not in [p.rstrip("\\/").casefold() for p in old.split(";")]:
                winreg.SetValueEx(key, "Path", 0, kind, old.rstrip(";") + ";" + str(target_dir))
        print("User PATH updated. Open a new terminal; sign out/in if the parent shell still has the old PATH.")
    elif str(target_dir) not in os.environ.get("PATH", "").split(os.pathsep):
        print('Add to your shell profile: export PATH="$HOME/.local/bin:$PATH"')
    print("Installed: loop, loop ros, loop-switch (loop robot and looper aliases retained)")
    print("User command directory: " + str(target_dir))
    print("Existing project configuration and runtime data were preserved.")


if __name__ == "__main__":
    main()
