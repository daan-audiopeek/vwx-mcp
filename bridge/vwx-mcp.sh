#!/usr/bin/env bash
# vwx-mcp server launcher for macOS (and Linux).
#
# Claude Desktop / Claude Code start this script themselves (stdio transport):
# you do not run it by hand. It talks to the TCP bridge inside Vectorworks on
# 127.0.0.1:9878, so start "VWX Bridge" in Vectorworks before asking Claude to
# do something there.
#
# Everything this script prints goes to stderr: on stdio, stdout belongs to
# the MCP protocol.
set -euo pipefail

VWXHOME="${VWXHOME:-$HOME/.local/share/vwx-mcp}"
VENV="$VWXHOME/.venv"

export DESKTOP_HOST="${DESKTOP_HOST:-127.0.0.1}"
export VWX_MCP_PORT="${VWX_MCP_PORT:-9878}"
export VWX_TRANSPORT="${VWX_TRANSPORT:-tcp}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-stdio}"
# full | gis | modeling | baumkataster | minimal
export VWX_TOOLSET="${VWX_TOOLSET:-full}"

if [ ! -x "$VENV/bin/python" ]; then
    echo "[vwx-mcp] First run: creating venv in $VENV ..." >&2
    if command -v uv >/dev/null 2>&1; then
        uv venv --python 3.12 "$VENV" >&2
        uv pip install --python "$VENV/bin/python" -r "$VWXHOME/requirements.txt" >&2
    else
        PY=""
        for cand in python3.13 python3.12 python3.11 python3.10 python3; do
            if command -v "$cand" >/dev/null 2>&1 &&
               "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
                PY="$cand"; break
            fi
        done
        if [ -z "$PY" ]; then
            echo "[vwx-mcp] Need Python 3.10+ (or uv). Install uv: https://docs.astral.sh/uv/" >&2
            exit 1
        fi
        "$PY" -m venv "$VENV" >&2
        "$VENV/bin/python" -m pip install --upgrade pip >&2
        "$VENV/bin/python" -m pip install -r "$VWXHOME/requirements.txt" >&2
    fi
fi

if [ "${VWX_SETUP_ONLY:-0}" = "1" ]; then
    echo "[vwx-mcp] venv ready: $VENV" >&2
    exit 0
fi

exec "$VENV/bin/python" "$VWXHOME/vwx_mcp_server.py"
