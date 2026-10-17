# CLAUDE.md — project context

## What this repo is

A fork of [vicquick/vwx-mcp](https://github.com/vicquick/vwx-mcp): an MCP server
that drives a live **Vectorworks 2026** session through `vs.*` Python running
inside VW. Upstream is Windows-first (native C++ palette + file IPC, bridge v13).

**This fork targets macOS.** On macOS the native palette does not exist, so the
chain is always the **TCP dialog bridge**:

```
Claude Code / Desktop ──stdio──▶ ~/.local/share/vwx-mcp/vwx-mcp.sh → mcp-server/vwx_mcp_server.py
                      ──JSON/TCP 127.0.0.1:9878──▶ "VWX Bridge" menu command
                      → vwx-plugin/vwx_mcp_bridge.py (modal pump dialog) → commands.py → vs.*
```

- `VWX_TRANSPORT` defaults to `tcp` on non-Windows; the file-IPC path, `native/`,
  `*.bat` and `BridgeStart_MenuCommand.py` are upstream/Windows and not used here.
- The bridge dialog is **modal**: while it runs the user cannot draw. Work in
  sessions (start bridge → let the agent work → Stop).
- Win32-only verbs are unavailable: `screenshot`, `list_documents`,
  `switch_document`, background operation.
- Install/update: `./bridge/install-macos.sh [year]` (see `docs/MACOS.md`).
  VW-side files land in `~/Library/Application Support/Vectorworks/2026/Plug-ins/VWX-MCP/`.
  `commands.py` hot-reloads on every TCP call (`importlib.reload`); server
  changes need a client restart.
- Logs: `…/Plug-ins/VWX-MCP/bridge.log`, `~/Library/Logs/Claude/mcp-server-vwx-mcp.log`.

## Goal of this fork

Build a **Spotlight toolset** (Vectorworks Spotlight / entertainment design):
lighting devices, DMX patch, channels and plot QC. The plan lives in
**[docs/SPOTLIGHT_PLAN.md](docs/SPOTLIGHT_PLAN.md)** — read it before working on
Spotlight verbs, and keep it updated as phases land.

## Read first

- **[AGENTS.md](AGENTS.md)** — access layers, UUID addressing, and the VW2026
  API gotchas (silent failures: null UUIDs, no-op draws, hanging handle walks).
  Follow it when writing any `vs.*` code.
- `docs/MACOS.md` — macOS install and operation.
- `docs/ARCHITECTURE.md` — upstream Windows bridge; background only.

## Layout

| Path | Role |
|---|---|
| `vwx-plugin/commands.py` | all `vs.*` verbs; pump finds them via `getattr(commands, name)` and passes a param dict |
| `vwx-plugin/vwx_mcp_bridge.py`, `BridgeTCP_MenuCommand.py` | macOS TCP bridge + menu-command bootstrap |
| `vwx-plugin/vs_index.json` | signature index of all 3071 `vs.*` functions (71 in category `Spotlight`) |
| `mcp-server/vwx_mcp_server.py` | fastmcp 3.x server; tools are `@vtool` wrappers calling `cmd("verb", {...})` |
| `mcp-server/tool_tags.py` | tool → tag map + `VWX_TOOLSET` presets |
| `tools/pruefe_konsistenz.py` | AST consistency check: server ↔ commands ↔ tags (exit 1 on findings) |
| `tools/build_vs_index.py` | rebuild the index from the SDK `vs.py` stub |

## Working rules

- New tool = verb in `commands.py` + `@vtool` wrapper + entry in `TOOL_TAGS`
  (checklist in AGENTS.md). Run `python tools/pruefe_konsistenz.py .` before committing.
- Look up signatures with `vs_signature` / `vs_index.json` instead of guessing
  arity — a wrong `vs.*` call raises a modal VW error dialog that blocks the bridge.
- Collect handles first, mutate after; never mutate inside `ForEachObject`.
  No `while h: h = vs.NextObj(h)` loops.
- Only `@vtool` / `@mcp.tool(output_schema=None)` — never emit an `outputSchema`.
- There is no CI that can reach VW. Keep pure logic (QC rules, patch maths)
  separate from `vs.*` calls so it can be tested in plain Python; everything
  else must be smoke-tested against a live VW on macOS, and say so when it wasn't.
- Tool counts in docs drift (README says 248, MACOS.md 283; `grep -c "@vtool"`
  currently gives 284). Count from the code, not the docs.
- Code comments in the codebase are a mix of English and German; match the
  surrounding file.
