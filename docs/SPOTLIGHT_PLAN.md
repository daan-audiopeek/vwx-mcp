# Spotlight toolset — plan

Status: **phase 0 done (except multi-cell/accessories), phase 1 done and live-tested, phase 2 done and live-tested (single device).** Target: Vectorworks 2026 Spotlight on
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
   *Answered in the phase-2 live test:* `LDevice_SetParam*` changes nothing;
   `SetRField` works, but the derived patch fields must be written too.
6. Which of `LightingInv*/Univ*/SL_Export` open a modal dialog.

### Running the discovery

The verb `spotlight_discover` (in `commands.py`, reachable via the `vwx`
dispatcher; deliberately no `@vtool` — it is a one-off tool) does all of the
above **read-only**. On the Mac:

1. `git pull && ./bridge/install-macos.sh` (deploys the new `commands.py`).
2. Open a **copy** of the drawing in VW2026, run **VWX Bridge**, `ping`.
3. `vwx("spotlight_discover", {})` — records, PIO kinds, cells, accessories,
   nesting. No `LDevice_*` probing, so no risk of error dialogs.
4. `vwx("spotlight_discover", {"probe": "one"})` — probes ~36 candidate
   universal names plus the device's own field names on the **first** device.
   An unknown name may raise VW's error dialog (nothing auto-dismisses it on
   macOS): click OK and note it. If it stays quiet, `{"probe": "all"}`.
5. The dump lands in
   `~/Library/Application Support/Vectorworks/2026/Plug-ins/VWX-MCP/spotlight_discovery.json`
   (each run overwrites it; pass `out_path` to keep several). Large plots:
   limit with `{"layers": ["…"]}`; every layer's scan time is in the dump.
6. `{"anonymize": true}` hashes all text values (document name, positions,
   purposes, notes) and keeps numbers readable — use this if the dump goes
   into the repo.

Output: a field map committed as `vwx-plugin/spotlight_fields.json`
(our canonical key → VW universal name → type), and a new "Spotlight" section
in AGENTS.md's gotcha table. Everything after this phase reads names from that
map, never from string literals scattered through the verbs.

### Results, run 1 (Franciscus main drawing, 2026-10-17)

Dump: `docs/discovery/franciscus_probe_all_anon.json`. VW 2026 31.3.0, Dutch
UI, 7 design layers, 1.5–1.9 s per full scan, no error dialogs (unknown
universal names fail silently, they do not pop a dialog). Field map:
`vwx-plugin/spotlight_fields.json`; gotchas in AGENTS.md ("Spotlight").

- 36 `Lighting Device`, 46 `Light Position Obj`, 92 `TrussItem`, 1 `Video Screen`.
  All devices single-cell, no accessories → cells/accessories still unverified.
- Patch is in use: universes 1–4, footprints 2–90. **Channel, Purpose, Dimmer,
  Circuit, Focus are empty on every device.**
- Raw numbers already show the QC case: in universe 1, eight 18-ch devices
  start every 10 addresses (185, 195, …, 255) and six 13-ch devices every 5
  (351, 356, …, 376) → overlapping ranges per `Num Channels`. Either those
  fixtures run a smaller mode than the record says (`Fixture Mode` is empty
  on all devices), or the patch overlaps. **User: the real patch is correct**
  → `Num Channels` does not follow the mode actually used. Consequence for
  `check_patch`: footprint source per device = user footprint table
  (instrument type/mode → channels) > GDTF mode (if set) > `Num Channels`;
  an overlap that only exists via `Num Channels` is a *warning* ("footprint
  unverified"), not an error. `get_patch` reports the footprint source.
- **Channels are done on the console, not in VW** → `Channel` empty is not a
  QC finding; channel tools (4d) drop to optional/last, unit numbering stays.
- 2 devices are unpatched (`0/0`), no unit number, no position.
- Script bug found and fixed: the first run took the IFC record as "the device
  record", so `device_field_stats` and the field-name probe are wrong in this
  dump. Record values are complete and correct. **Rerun `{"probe": "one"}`**
  (no anonymize needed; not for the repo) to establish which record fields
  `LDevice_GetParam*` accepts.

### Results, run 2 (probe "one", 2026-10-17)

- **`LDevice_GetParamStr(h, 0, -1, '__Version')` crashes Vectorworks** (process
  gone, no exception, no dump written). Isolated by the local session with a
  per-call fsync log. Run 1 only survived because it probed the IFC record's
  fields. Fix: `_sl_probe_names` drops every `'__'` name, also from
  user-supplied candidates. Not tested: the other `'__'` fields — not needed,
  `GetRField` reads them.
- Safe: Str on the 147 other fields, Long on type 1, Real on 3/7/20, Bool on
  type 2, all getters on unknown names, and on the button fields.
- `LDevice_GetParam*` agrees with the record for Position, Unit Number,
  Universe, UniverseAddress, DMX/Absolute Address, Color, UID, Z Location
  (Real, plain number). It returns `''` for Inst Type, Device Type, Wattage,
  Symbol Name although the record has values → **GetRField is the read path**,
  `LDevice_*` only where cells/accessories force it. Field map v2.

### Results, run 3 (GDTF mode test, one device, 2026-10-17)

| Step | GDTF Fixture | GDTF Mode | Num Channels | DMX Address |
|---|---|---|---|---|
| baseline | FOS BAR PENTE | 90 Channels | 90 | 1 |
| mode → none | (empty) | (empty) | **90 (stale)** | 1 |
| other GDTF | ADJ Vizi Hex | Mode 1 | 15 | 1 |

Choosing a GDTF mode overwrites `Num Channels`; clearing it does not. Patch and
`Fixture Mode` are untouched. Footprint source order for `check_patch` is
therefore: user table > `Num Channels` **only if `GDTF Fixture Mode` is set**
> `Num Channels` as "unverified". Not tested: another mode of the same fixture.

Still open for phase 0: one multi-cell device and one device with
an accessory (in a copy); (GDTF mode question answered in run 3).

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
| `spotlight_info` | counts per Spotlight PIO kind; device summary: universes (devices, highest address), patched/unpatched, per position, per instrument type, footprint sources |
| `list_lighting_devices` | typed rows; filters `position`, `layer`, `class_name`, `instrument_type`, `device_type`, `purpose`, `color`, `universe`, `patched`, `search`; `fields`, `sort` (position/address/layer/instrument_type), `limit`/`offset` |
| `get_lighting_device` | typed row + all raw record fields + attached records + cell/accessory counts |
| `list_hanging_positions` | positions with numbering fields, x/y/z, linked devices (count, units), device position names without an object |
| ~~`list_focus_points`~~ | dropped for now: the test plot has no focus point objects, so the PIO name is unknown |

Built (2026-10-17): verbs in `commands.py` ("Spotlight read tools"), pure
logic in `vwx-plugin/spotlight_logic.py`, 18 tests in
`tests/test_spotlight_logic.py` on the run-1 records, tag `spotlight`, preset
`VWX_TOOLSET=spotlight`. Smoke-tested against a fake `vs` fed from the dump, then **live-tested on
the Franciscus copy (2026-10-17)**: every expected number matched; 5–26 ms
inside VW per call, ~0.6 s round trip via the bridge. Only tool fix: natural
sort (Trek6 before Trek10) for positions and device sorts. Multi-cell devices are listed once with a
note (per-cell fields unverified). `channel_range`/`selected` filters left
out (channels live on the console; selection can follow in phase 2).

### 4b. Write (phase 2)

| Tool | Does |
|---|---|
| `set_lighting_device_fields` | writable keys on given devices — `changes` [{object_id, fields}] or `object_ids` + `fields`; `dry_run` default |
| `bulk_set_lighting_fields` | same fields on every device matching the list filters; no filter needs `all_devices` |
| `reset_lighting_devices` | `LDevice_Reset` (fallback `ResetObject`) on ids / filter / all |
| `suggest_footprints` | per instrument type: record footprint, address gaps in the patch, suggested footprint + confidence, table entry |
| `set_footprint` | confirm (or remove) the real footprint of a type; scope `document` (default) or `global` |
| ~~accessories~~ | postponed until a drawing with accessories has been probed |

Write path: validate every change first (nothing is written if one is
invalid) → `SetRField` on the `Lighting Device` record → `LDevice_Reset` →
read-back of every written field (+ the derived patch fields when universe or
address changed). When universe or address changes, `Absolute Address` and
`UniverseAddress` are computed (`spotlight_logic.derived_patch`) and written
too, because Spotlight does not recompute them (live test below); the dry run
shows them as `patch_expected`, the write as `patch_after`, and they are part
of the read-back. Writable keys only (`spotlight_logic.WRITABLE`): no derived,
symbol/GDTF-owned or `'__'` fields. Every result carries `previous`; passing it
back as `changes` restores. Whether Cmd+Z undoes bridge writes is **unknown**
(the modal dialog may make the whole bridge session one undo step) — live test.
No overlap check on write yet: that is `check_patch` in phase 3.

Footprint table. **Document scope** (default): worksheet resource
`vwx-mcp Footprints` inside the drawing — columns Instrument type, Channels,
Note, Confirmed; not placed on any layer; travels with the file, so a copy or
rename keeps it. A hand-edited sheet is parsed; bad rows are reported
(`sheet_problems`) and block `set_footprint` until fixed. **Global scope**:
`spotlight_footprints.json` next to `commands.py` (local to the Mac). Entries
the first version stored per file name in that local file are still read
(`legacy_entries`) and move into the drawing's sheet on the next
`set_footprint`. Key = instrument type (fallback: symbol name). Precedence in
every read tool: document sheet > global (`user`) > `Num Channels` with GDTF
mode (`gdtf_mode`) > `Num Channels` (`record_unverified`).
`suggest_footprints` always infers from the record values, so an entry never
hides the evidence. On the Franciscus data it suggests exactly 5 (Cameo TS60,
6 devices, record 13) and 10 (FOS IQ Par, 8 devices, record 18), confidence
high.

`save_first` (write tools and `set_footprint`): saves the drawing with the
Save menu command before the first write of a call, only when something will
actually change; refused for a never-saved drawing (Save would open the
Save-As dialog). Default off: saving also removes "revert to saved" as a way
back. Added after VW crashed once mid-test and lost an unsaved write.

Built 2026-10-17: 28 tests green, smoke-tested against a fake `vs` (diff,
write, read-back, restore via `previous`, invalid-field refusal, footprint
table).

**Live test 2026-10-17** (Franciscus copy, VW 2026 31.3, macOS; device: unit
404, FOS Par Aurora, Trek34, 2/1):

| Step | Result |
|---|---|
| `suggest_footprints` | ✅ 5 and 10, high |
| `set_footprint` ×2, scope document | ✅ `spotlight_info` → 14 user, 7 gdtf_mode, 15 record_unverified |
| purpose `TEST`, user1 `claude`: dry run → write | ✅ 0 read-back mismatches, Object Info shows both; restore via `previous` ✅ |
| address 1 → 400 | ❌ first run: record had 400 but `Absolute Address` 513 and `UniverseAddress` `2/1`, read-back still 0 mismatches (derived fields were not checked) |
| `LDevice_SetParamStr/Long` as alternative | ❌ no effect at all (see AGENTS.md) |
| address 1 → 400 after `derived_patch` fix | ✅ `patch_after` 912 / `2/400`; Object Info shows universe 2, address 400, absolute 912; restore via `previous` ✅ |

Side findings: VW crashed once between a write and the user's check (cause
unknown; the unsaved write was lost — the footprint table survived because it
lives outside the drawing). The footprint table is keyed by **file name**, so
a renamed copy does not see its entries. `LDevice_GetParam*` lags behind
record writes until the bridge dialog closes. Cmd+Z on bridge writes: still
untested.

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

Real cases from the live test (Franciscus), to become test fixtures:

- 6 devices (301–306) on position "Trek1", no `Light Position Obj` of that
  name (positions run Trek6–Trek51) → *position name without object*.
- universe 1: 501–508 (footprint 18, every 10) and 301–306 (13, every 5)
  overlap — all `record_unverified`, the real patch is correct → must come out
  as *footprint unverified* warnings, **not** patch errors (false positives
  otherwise).
- `TotalHungWeight` 170 kg on Trek40/Trek9 with 0 devices, empty pipes
  32.5–45.5 kg → candidate rule *hung weight without devices* (info: something
  else hangs there, or the weight is stale).
- one position at z=5000 while the rest share another trim → candidate rule
  *trim outlier* (info).
- class/legend name not matching the instrument type (MH X25 vs MH 360) →
  candidate rule *class vs instrument type* (info, opt-in).

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
