#!/bin/sh
# Local source installer. No sudo, remote shell payloads or system Python changes.
set -eu
loop_source_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -n "${LOOP_PYTHON:-}" ]; then
    loop_python=$LOOP_PYTHON
elif [ -x "$loop_source_dir/.venv/bin/python" ]; then
    loop_python="$loop_source_dir/.venv/bin/python"
else
    loop_python=python3
fi
if ! command -v "$loop_python" >/dev/null 2>&1; then
    echo 'Python 3.10+ with pip/venv is required. Set LOOP_PYTHON to a compatible interpreter.' >&2
    exit 1
fi
exec "$loop_python" "$loop_source_dir/scripts/install.py" "$@"
