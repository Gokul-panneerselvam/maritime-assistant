#!/usr/bin/env bash
# Maritime Operations Assistant — Single-Command Launcher for Unix / macOS

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_EXE="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON_EXE="python3"
fi

exec "$PYTHON_EXE" "$SCRIPT_DIR/start.py" "$@"

