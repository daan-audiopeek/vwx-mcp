# vwx-mcp on macOS

The Windows build drives Vectorworks in the background through a native C++
palette. That palette is Windows-only, so macOS uses the **TCP dialog bridge**:
a Python menu command opens a small "VW MCP Bridge" dialog inside Vectorworks
and listens on `127.0.0.1:9878`. All 283 tools work through it.

The trade-off: the dialog is **modal**. While it is open, Claude can work in the
drawing and you cannot. Work in sessions: start the bridge, let Claude do the
job, click **Stop**, carry on drawing.

```
Claude Desktop / Claude Code
   │ stdio (Claude starts the server itself)
   ▼
~/.local/share/vwx-mcp/vwx-mcp.sh → vwx_mcp_server.py
   │ JSON over TCP 127.0.0.1:9878
   ▼
"VWX Bridge" menu command → vwx_mcp_bridge.py (modal pump dialog, main thread)
   │
   ▼
commands.py → vs.*
```

## Requirements

- Vectorworks 2026 on macOS
- Python 3.10+ **or** [uv](https://docs.astral.sh/uv/) (recommended: `brew install uv`)
- Claude Desktop and/or Claude Code

## Install

```bash
git clone https://github.com/<you>/vwx-mcp.git
cd vwx-mcp
./bridge/install-macos.sh          # or: ./bridge/install-macos.sh 2026
```

The script copies the Vectorworks side to
`~/Library/Application Support/Vectorworks/<year>/Plug-ins/VWX-MCP/`, installs the
server in `~/.local/share/vwx-mcp/`, registers it with Claude Code and Claude
Desktop, and puts the menu-command script on your clipboard.

If your Vectorworks user folder lives somewhere else (Vectorworks Preferences >
User Folders), point the script at it:

```bash
VWX_USER_ROOT="/path/to/folder/containing/2026" ./bridge/install-macos.sh 2026
```

### One-time step in Vectorworks

1. **Tools > Plug-ins > Plug-in Manager > New…** → type **Menu Command**, name
   `VWX Bridge`.
2. **Edit Script…** → set the language to **Python** → paste the clipboard
   (the contents of `vwx-plugin/BridgeTCP_MenuCommand.py`) → OK.
3. **Tools > Workspaces > Edit Current Workspace** → drag `VWX Bridge` into a
   menu, optionally give it a shortcut (e.g. Cmd+Shift+B).
4. Restart Claude Desktop so it loads the new server.

## Use

1. Open a drawing in Vectorworks.
2. Run **VWX Bridge**. The dialog shows `Active v3.0 - TCP :9878`.
3. Ask Claude. Start with the `ping` tool to confirm the chain.
4. Click **Stop** when done.

## Update

```bash
git pull && ./bridge/install-macos.sh
```

`commands.py` hot-reloads on every call, so most updates work without
restarting the bridge. Restart Claude Desktop after server changes.

## Not available on macOS

- `screenshot` (Win32 window capture)
- `list_documents` / `switch_document` (Win32 window list); only the active
  document is known
- Background operation, idle auto-close and wake-on-demand (native palette +
  watchdog)

## Troubleshooting

- **Claude says it cannot connect to Vectorworks**: the bridge dialog is not
  open. Run `VWX Bridge`.
- **Bridge log**: `~/Library/Application Support/Vectorworks/2026/Plug-ins/VWX-MCP/bridge.log`
- **Server log**: Claude Desktop > Settings > Developer > vwx-mcp, or
  `~/Library/Logs/Claude/mcp-server-vwx-mcp.log`
- **Too many tools for the client**: set `VWX_TOOLSET=minimal` (or `modeling`,
  `gis`) in `~/.local/share/vwx-mcp/vwx-mcp.sh`.
