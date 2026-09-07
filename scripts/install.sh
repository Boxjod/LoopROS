#!/bin/sh
# Local source installer. Bootstraps user-local uv when needed; no sudo or system Python changes.
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
    echo 'Python 3.8+ is required to start the uv bootstrap. Set LOOP_PYTHON to an interpreter.' >&2
    exit 1
fi
exec "$loop_python" "$loop_source_dir/scripts/install.py" "$@"
