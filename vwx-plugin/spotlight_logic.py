"""spotlight_logic.py — pure Spotlight logic, no `import vs`.

Turns raw record text (vs.GetRField: always a string, locale-formatted) into
typed device rows via spotlight_fields.json, and does filtering, sorting and
summaries on those rows. commands.py does the vs.* side and reloads this
module on every call, so edits here hot-reload like commands.py itself.

Kept free of vs so it runs in plain Python: tests/test_spotlight_logic.py
feeds it the real records from docs/discovery/.
"""
import json
import os
import re

_DIR = os.path.dirname(os.path.abspath(__file__))
FIELD_MAP_PATH = os.path.join(_DIR, 'spotlight_fields.json')

# vs.GetFldType codes, as recorded in the field map
T_INT, T_BOOL, T_REAL, T_TEXT, T_DIM, T_POPUP = 1, 2, 3, 4, 7, 8
T_ANGLE = (14, 20)

# Booleans come back localized (VW UI language), not as True/False.
_TRUE = {'true', 'wahr', 'waar', 'vrai', 'vero', 'verdadero', 'yes', 'ja', '1'}
_FALSE = {'false', 'falsch', 'onwaar', 'faux', 'falso', 'no', 'nee', 'nein', '0'}

_NUM = re.compile(r'-?\d[\d.,]*')


def load_field_map(path=None):
    with open(path or FIELD_MAP_PATH, encoding='utf-8') as f:
        return json.load(f)


def parse_number(text):
    """'0,61' -> 0.61, '41°' -> 41.0, '3810,175908' -> 3810.175908, '' -> None.

    Decimal comma is what a Dutch/German VW returns. With both separators the
    last one is the decimal mark ('1.234,5' / '1,234.5'). A lone '.' is read as
    decimal, so '1.450' is 1.45 — do not feed this thousands-grouped text;
    positions come from GetSymLoc3D instead of the X/Y/Z Location text.
    """
    if text is None:
        return None
    m = _NUM.search(str(text))
    if not m:
        return None
    s = m.group(0).rstrip('.,')
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    else:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def parse_bool(text):
    t = str(text or '').strip().lower()
    if t in _TRUE:
        return True
    if t in _FALSE:
        return False
    return None


def parse_value(text, ftype):
    """Record text -> Python value by field type. Empty text -> None."""
    if text is None or str(text).strip() == '':
        return None
    if ftype == T_INT:
        n = parse_number(text)
        return int(n) if n is not None else None
    if ftype == T_BOOL:
        return parse_bool(text)
    if ftype == T_REAL or ftype == T_DIM or ftype in T_ANGLE:
        return parse_number(text)
    return str(text)


def _as_int(v):
    """Universe and Unit Number are TEXT fields that normally hold digits."""
    if v is None:
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip()
    return int(s) if s.isdigit() else None


def footprint_info(row):
    """(channels, source). 'Num Channels' is only refreshed when a GDTF mode
    is chosen; clearing the mode leaves the old value (run 3 in the plan)."""
    n = row.get('footprint')
    if not n:
        return None, None
    if row.get('gdtf_mode'):
        return n, 'gdtf_mode'
    return n, 'record_unverified'


def is_patched(row):
    return bool(_as_int(row.get('universe'))) and bool(row.get('address'))


def device_row(raw, fmap, extra=None):
    """raw = {record field name: text} of the 'Lighting Device' record.
    Returns {canonical key: typed value} for every key in the field map, plus
    derived keys and whatever `extra` carries (object_id, layer, x/y/z, ...)."""
    row = {}
    for key, spec in fmap['lighting_device'].items():
        row[key] = parse_value(raw.get(spec['field']), spec.get('type'))
    row['universe_number'] = _as_int(row.get('universe'))
    row['unit_number'] = _as_int(row.get('unit'))
    row['patched'] = is_patched(row)
    fp, src = footprint_info(row)
    row['footprint_source'] = src
    if row['patched'] and fp:
        row['address_end'] = row['address'] + int(fp) - 1
    else:
        row['address_end'] = None
    if extra:
        row.update(extra)
    return row


def position_row(raw, fmap, extra=None):
    row = {}
    for key, spec in fmap['hanging_position'].items():
        row[key] = parse_value(raw.get(spec['field']), spec.get('type'))
    if extra:
        row.update(extra)
    return row


# ── filtering / sorting ─────────────────────────────────────────────────────

_TEXT_FILTERS = ('position', 'layer', 'class', 'instrument_type', 'device_type',
                 'purpose', 'color')


def _eq(a, b):
    return str(a or '').strip().lower() == str(b or '').strip().lower()


def matches(row, flt):
    """flt keys: position, layer, class, instrument_type, device_type, purpose,
    color (exact, case-insensitive; '' matches empty), universe (int),
    patched (bool), search (substring over all text values)."""
    for k in _TEXT_FILTERS:
        if k in flt and flt[k] is not None and not _eq(row.get(k), flt[k]):
            return False
    if flt.get('universe') is not None and row.get('universe_number') != int(flt['universe']):
        return False
    if flt.get('patched') is not None and bool(row.get('patched')) != bool(flt['patched']):
        return False
    s = flt.get('search')
    if s:
        s = str(s).lower()
        if not any(isinstance(v, str) and s in v.lower() for v in row.values()):
            return False
    return True


_DIGITS = re.compile(r'(\d+)')


def natural_key(text):
    """'Trek6' < 'Trek10' < 'Trek51': digit runs compare as numbers. Empty
    sorts last ('~' would not: it is just another character here)."""
    s = str(text or '').strip()
    if not s:
        return (1, ())
    return (0, tuple((0, int(t), '') if t.isdigit() else (1, 0, t.lower())
                     for t in _DIGITS.split(s) if t))


def _num_or_big(v):
    return v if isinstance(v, (int, float)) else float('inf')


SORTS = {
    'position': lambda r: (natural_key(r.get('position')), _num_or_big(r.get('unit_number')),
                           natural_key(r.get('unit'))),
    'address': lambda r: (_num_or_big(r.get('universe_number')), _num_or_big(r.get('address'))),
    'layer': lambda r: (natural_key(r.get('layer')), natural_key(r.get('position')),
                        _num_or_big(r.get('unit_number'))),
    'instrument_type': lambda r: (natural_key(r.get('instrument_type')),
                                  natural_key(r.get('position'))),
}


def sort_rows(rows, by='position'):
    if by not in SORTS:
        raise ValueError('sort must be one of %s' % sorted(SORTS))
    return sorted(rows, key=SORTS[by])


def select_fields(row, fields):
    if not fields:
        return row
    keep = set(fields) | {'object_id'}
    return {k: v for k, v in row.items() if k in keep}


# ── summaries ────────────────────────────────────────────────────────────────

def summarize(rows):
    """Counts the agent needs to orient itself in a plot."""
    universes, positions, types, sources = {}, {}, {}, {}
    for r in rows:
        u = r.get('universe_number')
        if r.get('patched'):
            e = universes.setdefault(u, {'devices': 0, 'highest_address': 0})
            e['devices'] += 1
            e['highest_address'] = max(e['highest_address'], r.get('address_end') or r.get('address') or 0)
        p = r.get('position') or ''
        positions[p] = positions.get(p, 0) + 1
        t = r.get('instrument_type') or ''
        types[t] = types.get(t, 0) + 1
        s = r.get('footprint_source') or 'none'
        sources[s] = sources.get(s, 0) + 1
    return {
        'devices': len(rows),
        'patched': sum(1 for r in rows if r.get('patched')),
        'unpatched': sum(1 for r in rows if not r.get('patched')),
        'with_channel': sum(1 for r in rows if r.get('channel')),
        'multi_cell': sum(1 for r in rows if (r.get('cells') or 1) > 1),
        'with_accessories': sum(1 for r in rows if r.get('accessories')),
        'universes': {str(k): v for k, v in sorted(universes.items(), key=lambda kv: kv[0] or 0)},
        'positions': dict(sorted(positions.items())),
        'instrument_types': dict(sorted(types.items())),
        'footprint_sources': sources,
    }


def sort_positions(positions):
    return sorted(positions, key=lambda r: (natural_key(r.get('name')), natural_key(r.get('layer'))))


def link_positions(positions, devices):
    """Attach device counts to positions by name (devices are not nested in
    their position; the link is the text field Position = Position Name)."""
    by_name = {}
    for d in devices:
        by_name.setdefault(str(d.get('position') or '').strip().lower(), []).append(d)
    names = set()
    for p in positions:
        key = str(p.get('name') or '').strip().lower()
        names.add(key)
        ds = by_name.get(key, []) if key else []
        p['device_count'] = len(ds)
        units = sorted(d['unit_number'] for d in ds if d.get('unit_number') is not None)
        p['units'] = units
    orphans = sorted({str(d.get('position')) for d in devices
                      if d.get('position') and str(d['position']).strip().lower() not in names})
    return {
        'devices_without_position': sum(1 for d in devices if not d.get('position')),
        'device_positions_without_object': orphans,
    }


# ── writes (phase 2): validation and diffs, no vs ───────────────────────────

# Canonical keys a write tool may set. Everything else is derived by Spotlight
# (absolute_address, universe_address, cells, …), owned by the symbol/GDTF
# (instrument_type, footprint, gdtf_*), or internal ('__' fields: reading them
# through LDevice_* crashes VW, and writing them is not ours to do).
WRITABLE = ('unit', 'channel', 'universe', 'address', 'position', 'purpose',
            'color', 'gobo', 'gobo2', 'dimmer', 'circuit_number', 'circuit_name',
            'focus', 'user1')


def validate_fields(fields, fmap):
    """{canonical key: value} -> ({record field: text to write}, [errors]).
    None or '' clears a field. universe and address must be whole numbers
    (universe 0..32767, address 0..512; 0 or '' unpatches). Universe and
    address may be set on their own; the read-back shows what Spotlight made
    of it."""
    out, errors = {}, []
    spec = fmap['lighting_device']
    for key, value in (fields or {}).items():
        if key not in spec:
            errors.append('unknown field %r' % key)
            continue
        if key not in WRITABLE:
            errors.append('field %r is not writable (derived, symbol/GDTF-owned or internal)' % key)
            continue
        field = spec[key]['field']
        if field.startswith('__'):
            errors.append('field %r maps to an internal field' % key)
            continue
        text = '' if value is None else str(value).strip()
        if key in ('universe', 'address') and text != '':
            if not text.isdigit():
                errors.append('%s must be a whole number, got %r' % (key, value))
                continue
            n = int(text)
            lo, hi = (0, 32767) if key == 'universe' else (0, 512)
            if not lo <= n <= hi:
                errors.append('%s %d out of range %d..%d' % (key, n, lo, hi))
                continue
            text = str(n)
        out[field] = text
    return out, errors


def field_to_key(fmap):
    return {s['field']: k for k, s in fmap['lighting_device'].items()}


def diff_device(raw, to_write):
    """{record field: (old, new)} for fields that actually change."""
    return {f: (raw.get(f, ''), v) for f, v in to_write.items()
            if str(raw.get(f, '') or '') != v}


def readback_mismatches(after_raw, to_write):
    """Fields whose read-back text differs from what was written."""
    return {f: {'wrote': v, 'reads': after_raw.get(f, '')}
            for f, v in to_write.items() if str(after_raw.get(f, '') or '') != v}


# ── footprints (phase 2): table + inference from patch spacing ──────────────

FOOTPRINT_TABLE = os.path.join(_DIR, 'spotlight_footprints.json')


def footprint_key(row):
    """Footprints are per instrument type; fall back to the symbol name."""
    return str(row.get('instrument_type') or row.get('symbol') or '').strip()


def load_footprints(path=None):
    """{'documents': {doc: {type: entry}}, 'global': {type: entry}}. Missing
    or unreadable file -> empty table (a bad table must not break reads)."""
    try:
        with open(path or FOOTPRINT_TABLE, encoding='utf-8') as f:
            t = json.load(f)
    except Exception:
        t = {}
    t.setdefault('documents', {})
    t.setdefault('global', {})
    return t


def save_footprints(table, path=None):
    p = path or FOOTPRINT_TABLE
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(table, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, p)


def footprint_lookup(table, document, key):
    """Entry for one instrument type: this document first, then global."""
    if not key or not table:
        return None
    return (table.get('documents', {}).get(document or '', {}).get(key)
            or table.get('global', {}).get(key))


def set_footprint(table, document, key, channels, scope='document', note=None, when=None):
    """Confirm (channels int) or remove (channels None) one entry. Returns table."""
    if scope not in ('document', 'global'):
        raise ValueError("scope must be 'document' or 'global'")
    if not key:
        raise ValueError('instrument_type required')
    bucket = (table['documents'].setdefault(document or '', {}) if scope == 'document'
              else table['global'])
    if channels is None:
        bucket.pop(key, None)
    else:
        n = int(channels)
        if not 1 <= n <= 512:
            raise ValueError('channels must be 1..512')
        bucket[key] = {'channels': n, 'source': 'user', 'note': note, 'confirmed': when}
    return table


def apply_footprints(rows, table, document):
    """Recompute footprint, footprint_source and address_end with the table.
    Order: user table > Num Channels with a GDTF mode > Num Channels unverified."""
    for r in rows:
        e = footprint_lookup(table, document, footprint_key(r))
        if e:
            r['footprint'] = e['channels']
            r['footprint_source'] = 'user'
        if r.get('patched') and r.get('footprint'):
            r['address_end'] = r['address'] + int(r['footprint']) - 1
    return rows


def infer_footprints(rows):
    """Per instrument type: the address gaps to the next device of the SAME
    type in the same universe (consecutive in the patch). A run of equal gaps
    smaller than the record footprint is the evidence that the real mode is
    smaller. Never a fact — a suggestion the user confirms with set_footprint."""
    by_u = {}
    for r in rows:
        if r.get('patched'):
            by_u.setdefault(r['universe_number'], []).append(r)
    gaps, recs, counts = {}, {}, {}
    for us in by_u.values():
        us.sort(key=lambda r: r['address'])
        for a, b in zip(us, us[1:]):
            ka, kb = footprint_key(a), footprint_key(b)
            if ka and ka == kb:
                gaps.setdefault(ka, []).append(b['address'] - a['address'])
    for r in rows:
        k = footprint_key(r)
        if not k:
            continue
        counts[k] = counts.get(k, 0) + 1
        if r.get('footprint'):
            recs.setdefault(k, set()).add(int(r['footprint']))
    out = []
    for k in sorted(counts, key=natural_key):
        g = gaps.get(k, [])
        rec = sorted(recs.get(k, set()))
        entry = {'instrument_type': k, 'devices': counts[k], 'record_footprints': rec,
                 'gaps': sorted(set(g)), 'suggested': None, 'confidence': None,
                 'reason': None}
        if not g:
            entry['reason'] = 'no consecutive devices of this type in the patch'
        else:
            smallest = min(g)
            if rec and smallest >= max(rec):
                entry['reason'] = 'record footprint fits the patch spacing'
            else:
                entry['suggested'] = smallest
                same = g.count(smallest)
                entry['confidence'] = 'high' if same >= 3 and len(set(g)) == 1 else (
                    'medium' if same >= 2 else 'low')
                entry['reason'] = ('%d gap(s) of %d addresses, record says %s'
                                   % (same, smallest, '/'.join(map(str, rec)) or '?'))
        out.append(entry)
    return out
