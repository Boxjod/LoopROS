"""Install into the project venv; preserve conflicting launchers unless replacement is requested."""
from pathlib import Path
import argparse
import os
import platform
import subprocess
import shutil
import tempfile
import urllib.request
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from install_support import venv_python, windows_launcher, ensure_uv, backup_launcher


def validate_environment(environment):
    python = venv_python(environment)
    if environment.exists() or environment.is_symlink():
        try:
            result = subprocess.run(
                [str(python), "-c", "import sys; sys.exit(sys.version_info < (3, 10))"],
                capture_output=True, timeout=15)
            if result.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise SystemExit("Existing .venv is unusable or below Python 3.10; preserved at "
                         + str(environment) + ". Move it aside and rerun to create a uv environment.")
    return False



def main():
    parser = argparse.ArgumentParser(description="Install Loop ROS — Loop Robot Operating System")
    parser.add_argument("--terminal-only", action="store_true", help="Skip local MuJoCo/NumPy installation")
    parser.add_argument("--check", action="store_true", help="Print environment and exit without installing")
    parser.add_argument("--replace-launchers", action="store_true",
                        help="Back up conflicting user launchers and point commands to this checkout")
    args = parser.parse_args()
    print("Loop ROS | {} {} | Python {} | {}".format(platform.system(), platform.release(), platform.python_version(), platform.machine()))
    windows = os.name == "nt"
    if windows and tuple(sys.getwindowsversion()[:2]) < (6, 3):
        raise SystemExit("Native Windows 7/8 is not supported. Use SSH to a supported Loop ROS host.")
    root = ROOT
    environment = root / ".venv"
    python = venv_python(environment)
    existing = validate_environment(environment)
    target_dir = Path.home() / ".local/bin"
    # Validate all destinations before downloading or installing.
    names = ("loop", "loop-switch", "looper", "looper-switch")
    def owned_link(link, name):
        if not link.is_symlink():
            return False
        return Path(os.readlink(link)) in (environment / "bin" / name,
                                  root.parent / "loop_robot" / ".venv/bin" / name,
                                  root.parent / "looper_M1" / ".venv/bin" / name)
    def conflicting(link, name):
        if not (link.exists() or link.is_symlink()):
            return False
        if windows:
            if link.is_symlink() or not link.is_file():
                return True
            try:
                return link.read_text(encoding="utf-8") != windows_launcher(python.parent / (name + '.exe'))
            except UnicodeError:
                return True
        return not owned_link(link, name)

    for name in names:
        link = target_dir / (name + ".cmd" if windows else name)
        if conflicting(link, name):
            if not args.replace_launchers:
                raise SystemExit("Destination already exists; left unchanged: " + str(link)
                                 + "\nTo back up existing launchers and switch to this checkout, rerun with --replace-launchers.")
            if link.is_dir() and not link.is_symlink():
                raise SystemExit("Destination is a directory; left unchanged: " + str(link))
            print("Will back up and replace launcher: " + str(link))
    if args.check:
        print("Existing Python 3.10+ .venv will be reused." if existing else
              "Ready to bootstrap: uv will create .venv with Python 3.12 (downloads may be required).")
        print("No changes made; network, OS and binary compatibility are not certified.")
        return
    uv = ensure_uv()
    if not existing:
        print("Creating .venv with uv and Python 3.12...", flush=True)
        subprocess.run([uv, "venv", "--python", "3.12", str(environment)], check=True)
    subprocess.run([uv, "pip", "install", "--python", str(python), "-e",
                    str(root) + ("" if args.terminal_only else "[sim]")], check=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        link = target_dir / (name + ".cmd" if windows else name)
        # Recheck after dependency installation before changing any destination.
        if conflicting(link, name):
            if not args.replace_launchers or (link.is_dir() and not link.is_symlink()):
                raise SystemExit("Destination changed during installation; left unchanged: " + str(link))
            backup_launcher(link)
        if windows:
            link = target_dir / (name + ".cmd")
            content = windows_launcher(python.parent / (name + '.exe'))
            if not link.exists():
                link.write_text(content, encoding="utf-8")
            continue
        link = target_dir / name
        if link.is_symlink() and Path(os.readlink(link)) != environment / "bin" / name:
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
    try:
        main()
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit("Installation failed: {}. Check network access and uv/platform compatibility, then rerun.".format(exc)) from None
