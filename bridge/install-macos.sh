#!/usr/bin/env bash
# One-time (and re-runnable) macOS install for vwx-mcp.
#
#   git clone <your fork> && cd vwx-mcp && ./bridge/install-macos.sh [VW year]
#
# 1. copies the Vectorworks side to
#    ~/Library/Application Support/Vectorworks/<year>/Plug-ins/VWX-MCP/
# 2. copies the MCP server to ~/.local/share/vwx-mcp/ and builds its venv
# 3. registers the server with Claude Code (if the `claude` CLI is installed)
#    and with Claude Desktop (claude_desktop_config.json, backup kept)
# 4. puts the "VWX Bridge" menu-command script on the clipboard
#
# Re-run after every `git pull` to deploy the new version.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VW_ROOT="${VWX_USER_ROOT:-$HOME/Library/Application Support/Vectorworks}"
VWXHOME="${VWXHOME:-$HOME/.local/share/vwx-mcp}"

say() { printf '\033[1m[vwx-mcp]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[vwx-mcp] %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(uname)" = "Darwin" ] || say "Not macOS — continuing anyway (paths assume macOS)."

# --- Vectorworks version ----------------------------------------------------
VW_YEAR="${1:-${VWX_VW_VERSION:-}}"
if [ -z "$VW_YEAR" ]; then
    VW_YEAR="$(ls -1 "$VW_ROOT" 2>/dev/null | grep -E '^[0-9]{4}$' | sort -r | head -n1 || true)"
fi
[ -n "$VW_YEAR" ] || die "No Vectorworks user folder found in '$VW_ROOT'.
Start Vectorworks once, or check Settings > Vectorworks Preferences > User Folders
and run: VWX_USER_ROOT='<folder that contains 2026>' $0 2026"
PLUGIN_DIR="$VW_ROOT/$VW_YEAR/Plug-ins/VWX-MCP"
say "Vectorworks $VW_YEAR → $PLUGIN_DIR"

# --- 1. Vectorworks side ----------------------------------------------------
mkdir -p "$PLUGIN_DIR"
for f in vwx_mcp_bridge.py commands.py vwx_pump.py vs_index.json BridgeTCP_MenuCommand.py; do
    cp "$REPO/vwx-plugin/$f" "$PLUGIN_DIR/"
done
say "Bridge files copied."

# --- 2. MCP server ----------------------------------------------------------
mkdir -p "$VWXHOME"
cp "$REPO/mcp-server/vwx_mcp_server.py" "$REPO/mcp-server/tool_tags.py" \
   "$REPO/mcp-server/requirements.txt" "$VWXHOME/"
cp "$REPO/bridge/vwx-mcp.sh" "$VWXHOME/vwx-mcp.sh"
chmod +x "$VWXHOME/vwx-mcp.sh"
# Requirements may have changed since the last install: rebuild the venv.
if [ -d "$VWXHOME/.venv" ] && ! cmp -s "$REPO/mcp-server/requirements.txt" "$VWXHOME/.venv/.requirements"; then
    rm -rf "$VWXHOME/.venv"
fi
VWX_SETUP_ONLY=1 VWXHOME="$VWXHOME" "$VWXHOME/vwx-mcp.sh"
cp "$REPO/mcp-server/requirements.txt" "$VWXHOME/.venv/.requirements"
say "Server installed in $VWXHOME."

# --- 3a. Claude Code --------------------------------------------------------
if command -v claude >/dev/null 2>&1; then
    claude mcp remove --scope user vwx-mcp >/dev/null 2>&1 || true
    claude mcp add --scope user vwx-mcp -- "$VWXHOME/vwx-mcp.sh" \
        && say "Registered with Claude Code (user scope)."
else
    say "Claude Code CLI not found — skip. Later: claude mcp add --scope user vwx-mcp -- \"$VWXHOME/vwx-mcp.sh\""
fi

# --- 3b. Claude Desktop -----------------------------------------------------
DESKTOP_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [ -d "$(dirname "$DESKTOP_CFG")" ]; then
    [ -f "$DESKTOP_CFG" ] && cp "$DESKTOP_CFG" "$DESKTOP_CFG.bak-vwx-mcp"
    "$VWXHOME/.venv/bin/python" - "$DESKTOP_CFG" "$VWXHOME/vwx-mcp.sh" <<'PY'
import json, os, sys
cfg_path, launcher = sys.argv[1], sys.argv[2]
cfg = {}
if os.path.exists(cfg_path):
    with open(cfg_path, encoding="utf-8") as f:
        txt = f.read().strip()
    cfg = json.loads(txt) if txt else {}
cfg.setdefault("mcpServers", {})["vwx-mcp"] = {"command": launcher}
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
PY
    say "Registered with Claude Desktop (restart Claude Desktop to load it)."
else
    say "Claude Desktop not found — skip."
fi

# --- 4. Menu command script on the clipboard --------------------------------
if command -v pbcopy >/dev/null 2>&1; then
    pbcopy < "$REPO/vwx-plugin/BridgeTCP_MenuCommand.py"
    say "The 'VWX Bridge' menu-command script is on your clipboard."
fi

cat <<EOF

Done. One-time step in Vectorworks $VW_YEAR (see docs/MACOS.md):
  Tools > Plug-ins > Plug-in Manager > New… > Menu Command, name "VWX Bridge",
  Edit Script → language Python → paste (Cmd+V) → OK.
  Then add "VWX Bridge" to a menu via Tools > Workspaces > Edit Current Workspace.

Use: open a drawing → run "VWX Bridge" → ask Claude → click Stop when done.
EOF
