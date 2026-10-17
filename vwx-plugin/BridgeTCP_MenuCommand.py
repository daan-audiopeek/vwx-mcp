# VWX Bridge (TCP) — macOS start command.
#
# Paste this as the script of a Python MENU COMMAND plug-in
# (Tools > Plug-ins > Plug-in Manager > New... > Menu Command, language Python),
# name it "VWX Bridge", add it to a menu in the workspace editor and give it a
# shortcut (e.g. Cmd+Shift+B).
#
# What it does: finds the VWX-MCP folder in your Vectorworks user folder and
# runs vwx_mcp_bridge.py from there. The bridge opens a small "VW MCP Bridge"
# dialog and listens on 127.0.0.1:9878. While that dialog is open, Claude can
# work in the drawing and the Vectorworks UI is locked. Click Stop to get the
# UI back; run this command again for the next Claude session.
#
# Why a dialog: Vectorworks' Python API only gives periodic main-thread
# callbacks to a modal layout dialog (see legacy/README.md). A background
# bridge needs the native C++ palette, which is Windows-only for now.
import os
import sys
import runpy


def _vw_user_roots():
    forced_root = os.environ.get('VWX_USER_ROOT')
    if forced_root:
        return [forced_root]
    roots = []
    if sys.platform == 'darwin':
        roots.append(os.path.expanduser('~/Library/Application Support/Vectorworks'))
    appdata = os.environ.get('APPDATA')
    if appdata:
        roots.append(os.path.join(appdata, 'Nemetschek', 'Vectorworks'))
    return roots


def _find_plugin_dir():
    forced = os.environ.get('VWX_PLUGIN_DIR')
    if forced and os.path.isdir(forced):
        return forced
    want = os.environ.get('VWX_VW_VERSION')
    for root in _vw_user_roots():
        try:
            versions = [want] if want else sorted(
                (d for d in os.listdir(root) if len(d) == 4 and d.isdigit()),
                reverse=True)
        except Exception:
            continue
        for v in versions:
            for name in ('VWX-MCP', 'VW-MCP'):
                cand = os.path.join(root, v, 'Plug-ins', name)
                if os.path.isfile(os.path.join(cand, 'vwx_mcp_bridge.py')):
                    return cand
    return None


_dir = _find_plugin_dir()
if _dir is None:
    import vs
    vs.AlrtDialog('VWX Bridge: no VWX-MCP folder with vwx_mcp_bridge.py found '
                  'in the Vectorworks user Plug-ins folder. Run '
                  'bridge/install-macos.sh again.')
else:
    os.environ['VWX_PLUGIN_DIR'] = _dir
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
    # run_path sets __file__, so the bridge resolves its own folder.
    runpy.run_path(os.path.join(_dir, 'vwx_mcp_bridge.py'),
                   run_name='__vwx_bridge__')
