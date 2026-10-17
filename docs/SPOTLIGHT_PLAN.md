# Spotlight toolset — plan

Status: **plan only, nothing built yet.** Target: Vectorworks 2026 Spotlight on
macOS via the TCP bridge (see `CLAUDE.md`).

Goal: let an agent read, patch, number and check a lighting plot — lighting
devices, DMX patch, channels and plot QC — through typed tools, without
`execute_script` and without silent failures.

## 1. What the API gives us

`vs_index.json` lists 71 functions in category `Spotlight`. The useful ones:

| Need | Functions |
|---|---|
| Read/write device fields by **worksheet (universal) name** | `LDevice_GetParamStr/Long/Real/Bool`, `LDevice_SetParam…` — `(handle, cellIndex, accessoryIndex, universalName[, value])` |
| Multi-cell devices (LED bars, multi-instrument) | `LDevice_GetCellCount` |
| Accessories | `LDevice_GetAccCount`, `LDevice_AddAccessory`, `LDevice_DeleteAcc`, `LDevice_Get/SetAccPos2D/3D`, `LDevice_SetAccCell` |
| Regenerate after edits | `LDevice_Reset`, `LDevice_ResetVisual` |
| Schematic views | `IsLDSchematicViewObj` (exclude from counts — same device, second object) |
| Light info from symbol | `ApplyLightInfoRecord` |
| Data exchange / visualizer | `SL_Export`, `SL_Import`, `SL_UpdateUID`, `Get/SetVisionMapping` |
| Inventory / universes | `LightingInvExport/Import`, `LightingUnivExport/Import` (likely open dialogs — verify) |
| Hoists (Braceworks) | `HO_GetNumHoistOrigin`, `HO_GetHoistOriginAt` |

Plus the generic layers we already have: `ForEachObject` with criteria
(`(PON='Lighting Device')`), `GetRField`/`SetRField` on the PIO record,
`GetObjectUuid`, worksheets with `=DATABASE(...)`, records.

Not in the API (UI only, do not try): Spotlight Preferences dialogs, Label
Legend layout editing, the Patch/Instrument Summary palettes, GDTF mode
selection dialogs.

## 2. Phase 0 — discovery spike (live, before any wrapper)

The VW2026 field names and PIO names must be **measured, not assumed** — every
wrong name is a silent `''` / no-op. One `execute_script` session on a real
Spotlight drawing (ideally a VW sample plot plus one of our own) to record:

1. PIO names in use: `Lighting Device`, hanging positions
   (`Light Position Obj` / `Hanging Position`?), `Focus Point`, `Truss`,
   `Label Legend`, `Video Screen`. Via `GetName(GetCustomObjectInfo…)` /
   `GetRecord(h,1)` on each `T=PLUGINOBJECT`.
2. Full field list of the `Lighting Device` record (`NumFields`/`GetFldName`)
   and which universal names `LDevice_GetParam*` accepts — at least: unit
   number, channel, universe, address / absolute address, DMX footprint,
   mode, fixture ID, position, purpose, instrument type, wattage, color,
   gobo 1/2, circuit name/number, dimmer, focus, symbol name, UID, weight.
3. How universe/address is stored (separate fields vs. absolute address
   `(u-1)*512+a`) and where the **footprint** comes from (GDTF mode vs. a
   plain field).
4. Behaviour of `cellIndex`/`accessoryIndex` (0 = device itself? 1-based
   cells?), and whether `SetParam…` needs `LDevice_Reset` to show.
5. Whether `SetRField` on the PIO record and `LDevice_SetParamStr` are
   equivalent, and which one keeps Spotlight's internal state consistent.
6. Which of `LightingInv*/Univ*/SL_Export` open a modal dialog.

Output: a field map committed as `vwx-plugin/spotlight_fields.json`
(our canonical key → VW universal name → type), and a new "Spotlight" section
in AGENTS.md's gotcha table. Everything after this phase reads names from that
map, never from string literals scattered through the verbs.

## 3. Architecture

- **`vwx-plugin/spotlight_logic.py`** (new, pure Python, no `import vs`):
  patch maths, overlap detection, numbering, all QC rules. Input = plain list
  of device dicts. Unit-testable on Linux/CI with `pytest`
  (`tests/test_spotlight_logic.py`) — the first part of this repo that can be
  tested without VW.
- **`commands.py`**: thin verbs — collect devices into dicts, call the logic,
  write back. Must `importlib.reload(spotlight_logic)` so hot-reload still works.
- **One collector** `_ld_collect(scope)` used by every read verb: one
  `ForEachObject` pass, skip schematic views, expand multi-cell devices into
  rows `(uuid, cell)`, read all mapped fields. Scope = all / layer / class /
  selection / position / UUID list. Hard `limit` like the existing collectors.
- **Writes**: collect-then-mutate, `LDevice_Reset` once per touched device
  after all fields are set, **`dry_run=True` by default** on every bulk write —
  returns the diff (`uuid`, field, old → new) so the agent shows it before
  applying.
- **Tag** `spotlight` in `tool_tags.py`; **preset** `VWX_TOOLSET=spotlight` =
  `{spotlight, records, query, layers, classes, worksheets, document, escape}`.

## 4. Tools

### 4a. Read (phase 1)

| Tool | Does |
|---|---|
| `spotlight_info` | Spotlight present? counts of devices / positions / focus points / accessories, universes in use, field-map version |
| `list_lighting_devices` | rows with the mapped fields; filters (`position`, `layer`, `class`, `instrument_type`, `universe`, `channel_range`, `selected`), `fields` subset, `limit` |
| `get_lighting_device` | one device incl. all cells and accessories |
| `list_hanging_positions` | positions with device count, trim height, layer |
| `list_focus_points` | focus points + how many devices point at each |

### 4b. Write (phase 2)

| Tool | Does |
|---|---|
| `set_lighting_device_fields` | set mapped fields on one or many UUIDs (`dry_run`) |
| `bulk_set_lighting_fields` | criteria/filter → fields (e.g. color `L201` on all units of `FOH 1`) |
| `add_lighting_accessory` / `remove_lighting_accessory` | via `LDevice_AddAccessory`/`DeleteAcc` |
| `reset_lighting_devices` | `LDevice_Reset` on scope (after manual record edits) |

Device placement (`create_lighting_device` from a symbol on a position) comes
later and only if phase 0 shows it can be done without the UI — it is the
same "insert PIO by script" problem that bit plant styles (AGENTS.md).

### 4c. Patch (phase 3)

| Tool | Does |
|---|---|
| `get_patch` | per universe: address ranges `[start, start+footprint-1]`, used/free count |
| `check_patch` | overlaps within a universe, address 0/unset, range > 512, footprint unknown, devices sharing an address with different modes |
| `auto_patch` | assign addresses for a scope: start universe/address, order (`position` then `unit`, or `channel`), gap, "don't split a footprint across universes"; keeps already patched devices unless `repatch=true`; `dry_run` |
| `find_free_addresses` | first free block of N addresses in universe U |

### 4d. Channels and numbering (phase 3)

| Tool | Does |
|---|---|
| `get_channel_hookup` | channel → devices (+ position/unit/purpose/color), sorted |
| `check_channels` | unassigned, duplicates (warning, not error — shared channels are legitimate), gaps, channel vs. purpose inconsistencies |
| `auto_number_units` | unit numbers per position, left→right / right→left by X along the position, start value; `dry_run` |
| `auto_number_channels` | channels by position order / by purpose groups / from a mapping; `dry_run` |

### 4e. Plot QC (phase 4)

`plot_qc` runs a rule set and returns findings `{rule, severity, uuid, message}`
plus a summary; `rules=[…]` and `severity` filter. First rules:

| Rule | Severity |
|---|---|
| device without hanging position / position name not matching any position | error |
| duplicate unit number within a position | error |
| missing channel | warning |
| patch overlap / address out of range (from `check_patch`) | error |
| device without focus point, or focus point without devices | warning |
| missing instrument type / symbol not found | error |
| empty color / gobo where the purpose implies one (configurable) | info |
| device on a layer/class outside the drawing's conventions (configurable lists) | warning |
| Z / trim height 0 for a device on a flown position | warning |
| schematic view without its source device | warning |

Rules are data (`spotlight_logic.RULES`), so a project-specific profile
(`qc_profile` dict) can switch rules off or change severities.

### 4f. Reports (phase 5)

| Tool | Does |
|---|---|
| `create_instrument_schedule` | Spotlight worksheet via the existing `create_report_worksheet` engine (`=DATABASE((PON='Lighting Device'))` + column formulas from the field map) |
| `export_lighting_csv` | channel hookup / instrument schedule / patch as CSV — written by the **server** process (macOS file system), so no VW export dialog |
| `export_lighting_exchange` | `SL_Export` / inventory export — only if phase 0 shows it runs without a dialog; otherwise listed with the dialog verbs in AGENTS.md |

## 5. Phases and done criteria

| Phase | Content | Done when |
|---|---|---|
| 0 | discovery spike, `spotlight_fields.json`, AGENTS.md gotchas | field map verified on ≥2 drawings incl. a multi-cell device |
| 1 | collector + read tools, tag + preset | read tools return correct data on the test drawings; `pruefe_konsistenz.py` clean |
| 2 | write tools with `dry_run` | write → read-back matches; device redraws after reset |
| 3 | patch + channels + numbering | logic unit tests green; `auto_patch` on a 50+ device plot gives zero overlaps in `check_patch` and in VW's own patch view |
| 4 | `plot_qc` | each rule has a unit test and a seeded live fault that it finds |
| 5 | reports / export | worksheet and CSV match the Spotlight instrument summary |

Each phase is one PR to `macos-support`, live-tested on macOS VW2026, with the
test drawing and results noted in the PR.

## 6. Risks and open questions

- **Field names / storage of patch data** — the whole toolset depends on
  phase 0. If `LDevice_*Param*` and the record disagree, follow what VW's own
  worksheets show.
- **Multi-cell devices and accessories** may carry their own channel/address;
  the row model `(uuid, cell)` must cover that from phase 1.
- **Modal bridge**: bulk writes on large plots block the UI for their duration;
  measure on a ~500-device drawing and add `limit`/batching if needed.
- **GDTF footprint**: if the footprint is only known via the GDTF mode and not
  readable, `check_patch` needs a user-supplied footprint table per instrument type.
- **Undo**: bulk writes should be one undo step if possible
  (`vs.SetUndoPoint`/equivalent — check in phase 0); otherwise `dry_run` is
  the only safety net.
- Test drawings: need a representative Spotlight plot from you (positions,
  multi-cell fixtures, GDTF devices, a few universes).
