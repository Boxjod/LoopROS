"""Build an audited public wheel and standalone uv bootstrap; never upload a working tree."""
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
from install_support import ensure_uv
from _version import __version__


def public_source(root, destination):
    """Build from tracked, non-ignored working files; never copy local packages."""
    root, destination = Path(root).resolve(), Path(destination)
    names = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z']).decode().split('\0')
    names = [name for name in names if name]
    ignored = subprocess.run(['git', '-C', str(root), 'check-ignore', '--no-index', '-z', '--stdin'],
                             input=('\0'.join(names)+'\0').encode(), capture_output=True)
    if ignored.returncode not in (0, 1):
        raise RuntimeError('Cannot audit release source ignore rules')
    excluded = set(ignored.stdout.decode().split('\0'))
    destination.mkdir(parents=True)
    for name in names:
        if name in excluded:
            continue
        source = root / name
        if source.is_symlink():
            raise ValueError('Release source symlinks require review: ' + name)
        if not source.is_file():
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if not (destination / 'pyproject.toml').is_file():
        raise ValueError('Tracked release source is incomplete')
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True, help='Final HTTPS public base URL')
    parser.add_argument('--output', required=True, help='New directory; existing paths refused')
    args = parser.parse_args()
    url = base_url(args.url)
    if any(char in url for char in "'\"`$\\\n\r "):
        parser.error('Use a plain HTTPS URL without shell metacharacters')
    output = Path(args.output).resolve()
    if output.exists():
        parser.error('Output already exists; choose a fresh release directory')
    with tempfile.TemporaryDirectory(prefix='loop-wheel-') as directory:
        source = public_source(ROOT, Path(directory) / 'source')
        subprocess.run([ensure_uv(), 'build', '--wheel', '--out-dir', directory, str(source)], check=True)
        wheel, = Path(directory).glob('loop_ros-*.whl')
        expected = 'loop_ros-' + __version__ + '-py3-none-any.whl'
        if wheel.name != expected:
            raise ValueError('Wheel version differs from the single version source')
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                parts = Path(name).parts
                if any(p in ('artifacts', '.loop', '.looper', '.venv', '__pycache__', 'candidates', 'user_skills', 'user_tools') for p in parts) or any(
                    p in name for p in ('credentials.json', 'config.local.json', '.sqlite', 'DEPLOYMENT.md')):
                    raise ValueError('Private/runtime file found in wheel: ' + name)
                if not name.startswith(('loop_robot/', 'loop_ros-' + __version__ + '.dist-info/')):
                    raise ValueError('Unexpected wheel entry: ' + name)
        output.mkdir(parents=True)
        shutil.copy2(wheel, output / wheel.name)
    metadata = {'version': __version__, 'wheel': expected, 'state_schema': 1,
                'sha256': hashlib.sha256((output / expected).read_bytes()).hexdigest()}
    (output / 'latest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    version_dir = output / 'versions' / __version__
    version_dir.mkdir(parents=True)
    shutil.copy2(output / 'latest.json', version_dir / 'latest.json')
    with zipfile.ZipFile(output / 'bootstrap.pyz', 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / 'release_client.py', '__main__.py')
        for name in ('install_support.py', 'release_runtime.py', '_version.py'):
            archive.write(ROOT / name, name)
    script = '''#!/bin/sh
# Loop ROS HTTPS release installer. No sudo; no system Python changes.
set -eu
loop_temp=$(mktemp -d)
trap 'rm -f "$loop_temp/bootstrap.pyz" "$loop_temp/uv.sh"; rmdir "$loop_temp"' EXIT HUP INT TERM
curl --fail --silent --show-error --proto '=https' --proto-redir '=https' --location --connect-timeout 15 --max-time 120 '__URL__/bootstrap.pyz' -o "$loop_temp/bootstrap.pyz"
loop_python=${LOOP_PYTHON:-python3}
if command -v "$loop_python" >/dev/null 2>&1 && "$loop_python" -c 'import sys; sys.exit(sys.version_info < (3,8))'; then
    "$loop_python" "$loop_temp/bootstrap.pyz" --url '__URL__' __ACTION__ "$@"
else
    loop_uv=$(command -v uv || true)
    if [ -z "$loop_uv" ]; then
        loop_uv="$HOME/.local/bin/uv"
        if [ ! -x "$loop_uv" ]; then
            curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 120 https://astral.sh/uv/install.sh -o "$loop_temp/uv.sh"
            UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh "$loop_temp/uv.sh"
        fi
    fi
    "$loop_uv" run --no-project --python 3.12 "$loop_temp/bootstrap.pyz" --url '__URL__' __ACTION__ "$@"
fi
'''.replace('__URL__', url)
    (output / 'install.sh').write_text(script.replace('__ACTION__', ''))
    (output / 'uninstall.sh').write_text(script.replace('__ACTION__', '--uninstall'))
    powershell = '''$ErrorActionPreference = 'Stop'
$loopTemp = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $loopTemp | Out-Null
try {
    $loopBundle = Join-Path $loopTemp 'bootstrap.pyz'
    Invoke-WebRequest -Uri '__URL__/bootstrap.pyz' -OutFile $loopBundle
    if ($env:LOOP_PYTHON) { & $env:LOOP_PYTHON $loopBundle --url '__URL__' @args }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { & py -3 $loopBundle --url '__URL__' @args }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python $loopBundle --url '__URL__' @args }
    else { throw 'Install Python 3.8+ or set LOOP_PYTHON, then rerun.' }
    if ($LASTEXITCODE -ne 0) { throw "Loop ROS installer exited with $LASTEXITCODE" }
} finally { Remove-Item -Recurse -Force $loopTemp }
'''.replace('__URL__', url)
    (output / 'install.ps1').write_text(powershell)
    from scripts.build_website import export_website
    export_website(output, url, __version__)
    # Immutable release-specific metadata; latest.json is published last by deployment.
    sums = []
    for path in sorted(output.rglob('*')):
        if path.is_file():
            sums.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.relative_to(output).as_posix())
    (output / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
    print('Public bundle: ' + str(output))


if __name__ == '__main__':
    main()
