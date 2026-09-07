"""Build a public-only directory; never upload a working tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from release_client import base_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Final HTTPS public base URL")
    parser.add_argument("--output", required=True, help="New directory; existing paths refused")
    args = parser.parse_args()
    url = base_url(args.url)
    if any(char in url for char in "'\"`$\\\n\r "):
        parser.error("Use a plain HTTPS URL without shell metacharacters")
    output = Path(args.output).resolve()
    if output.exists():
        parser.error("Output already exists; choose a fresh release directory")
    with tempfile.TemporaryDirectory(prefix="loop-wheel-") as directory:
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", directory, str(ROOT)], check=True)
        wheel, = Path(directory).glob("loop_ros-*.whl")
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                parts = Path(name).parts
                if any(p in ("artifacts", ".loop", ".looper", ".venv", "__pycache__") for p in parts) or any(p in name for p in ("credentials.json", "config.local.json", ".sqlite")):
                    raise ValueError("Private/runtime file found in wheel: " + name)
        output.mkdir(parents=True)
        shutil.copy2(wheel, output / wheel.name)
    release_version = wheel.name.split("-")[1]
    metadata = {"version": release_version, "wheel": wheel.name,
                "sha256": hashlib.sha256((output / wheel.name).read_bytes()).hexdigest()}
    (output / "latest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    shutil.copy2(ROOT / "release_client.py", output / "bootstrap.py")
    script = '''#!/bin/sh
set -eu
loop_python=${LOOP_PYTHON:-python3}
"$loop_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else "Python 3.10+ required")'
loop_temp=$(mktemp -d)
trap 'rm -f "$loop_temp/bootstrap.py"; rmdir "$loop_temp"' EXIT HUP INT TERM
curl --fail --silent --show-error --proto '=https' --proto-redir '=https' --location --connect-timeout 15 --max-time 120 '__URL__/bootstrap.py' -o "$loop_temp/bootstrap.py"
"$loop_python" "$loop_temp/bootstrap.py" --url '__URL__' "$@"
'''.replace("__URL__", url)
    (output / "install.sh").write_text(script)
    for name in ("index.html", "style.css", "site.js", "favicon.png"):
        shutil.copy2(ROOT / "website" / name, output / name)
    # Relative parent paths would escape a deployment subdirectory.
    index = (output / "index.html").read_text().replace("../logo.png", "logo.png").replace("../docs/", "docs/")
    index = index.replace("https://8.134.90.171/LoopROS", url).replace(
        "Download pending: HTTPS for 8.134.90.171 is not configured yet. This command is not available to run yet.",
        "Linux/macOS: copy the command above to download and install Loop ROS.")
    (output / "index.html").write_text(index)
    public_js = (output / "site.js").read_text().replace("https://8.134.90.171/LoopROS", url)
    (output / "site.js").write_text(public_js)
    shutil.copy2(ROOT / "logo.png", output / "logo.png")
    (output / "docs").mkdir()
    for name in ("INSTALL.md", "PLATFORMS.md", "USER_HOME.md", "QUICK_SETUP.md", "RELEASES.md"):
        shutil.copy2(ROOT / "docs" / name, output / "docs" / name)
    print("Public bundle: " + str(output))


if __name__ == "__main__":
    main()
