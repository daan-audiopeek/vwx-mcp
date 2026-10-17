"""Tests for vwx-plugin/spotlight_logic.py — plain Python, no Vectorworks.

Input is the real 'Lighting Device' record text from the first discovery run
(docs/discovery/franciscus_probe_all_anon.json, 36 devices). Text values there
are hashed ('txt:…'), numbers and booleans are not, so counts and patch data
are real. Run: python -m unittest discover -s tests
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'vwx-plugin'))
import spotlight_logic as sl  # noqa: E402

DUMP = os.path.join(ROOT, 'docs', 'discovery', 'franciscus_probe_all_anon.json')


def _rows():
    fmap = sl.load_field_map()
    with open(DUMP, encoding='utf-8') as f:
        dump = json.load(f)
    rows = []
    for d in dump['devices']:
        loc = d.get('loc3d') or [None, None, None]
        extra = {'object_id': d['object_id'], 'layer': d['layer'], 'class': d['class'],
                 'x': loc[0], 'y': loc[1], 'z': loc[2]}
        rows.append(sl.device_row(d['records']['Lighting Device'], fmap, extra))
    return fmap, dump, rows


class ParseTest(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(sl.parse_number('0,61'), 0.61)
        self.assertEqual(sl.parse_number('41°'), 41.0)
        self.assertEqual(sl.parse_number('3810,175908'), 3810.175908)
        self.assertEqual(sl.parse_number('1.234,5'), 1234.5)
        self.assertEqual(sl.parse_number('1,234.5'), 1234.5)
        self.assertEqual(sl.parse_number('-90'), -90.0)
        self.assertIsNone(sl.parse_number(''))
        self.assertIsNone(sl.parse_number('none'))

    def test_bools_any_locale(self):
        for t in ('True', 'Wahr', 'Waar', 'Vrai'):
            self.assertIs(sl.parse_bool(t), True)
        for t in ('False', 'Falsch', 'Onwaar', 'Faux'):
            self.assertIs(sl.parse_bool(t), False)
        self.assertIsNone(sl.parse_bool('txt:6:63f46a'))

    def test_value_by_type(self):
        self.assertEqual(sl.parse_value('351', sl.T_INT), 351)
        self.assertEqual(sl.parse_value('41°', 20), 41.0)
        self.assertEqual(sl.parse_value('Trek1', sl.T_TEXT), 'Trek1')
        self.assertIsNone(sl.parse_value('', sl.T_INT))
        self.assertIsNone(sl.parse_value('  ', sl.T_TEXT))


class FieldMapTest(unittest.TestCase):
    def test_no_internal_field_reaches_ldevice(self):
        # LDevice_GetParamStr on a '__' field crashes Vectorworks.
        fmap = sl.load_field_map()
        for key, spec in fmap['lighting_device'].items():
            if spec['field'].startswith('__'):
                self.assertIsNone(spec.get('ldevice'), key)

    def test_map_fields_exist_in_record(self):
        fmap, dump, _ = _rows()
        rec = dump['devices'][0]['records']['Lighting Device']
        for key, spec in fmap['lighting_device'].items():
            self.assertIn(spec['field'], rec, key)


class DeviceRowTest(unittest.TestCase):
    def setUp(self):
        self.fmap, self.dump, self.rows = _rows()

    def test_count_and_types(self):
        self.assertEqual(len(self.rows), 36)
        r = self.rows[0]
        self.assertIsInstance(r['address'], int)
        self.assertIsInstance(r['footprint'], int)
        self.assertEqual(r['z'], 1450.0)

    def test_absolute_address_consistent(self):
        for r in self.rows:
            if r['patched']:
                self.assertEqual(r['absolute_address'],
                                 (r['universe_number'] - 1) * 512 + r['address'])

    def test_patch_state(self):
        s = sl.summarize(self.rows)
        self.assertEqual(s['patched'], 34)
        self.assertEqual(s['unpatched'], 2)
        self.assertEqual(sorted(s['universes']), ['1', '2', '3', '4'])
        self.assertEqual(s['with_channel'], 0)

    def test_footprint_source(self):
        s = sl.summarize(self.rows)
        # 7 devices have a GDTF mode chosen (run 1); the rest is unverified.
        self.assertEqual(s['footprint_sources'].get('gdtf_mode'), 7)
        self.assertEqual(s['footprint_sources'].get('record_unverified'), 29)
        gdtf = [r for r in self.rows if r['footprint_source'] == 'gdtf_mode']
        self.assertTrue(all(r['footprint'] == 90 for r in gdtf))

    def test_address_end(self):
        r = next(r for r in self.rows if r['footprint_source'] == 'gdtf_mode')
        self.assertEqual(r['address_end'], r['address'] + 89)


class FilterSortTest(unittest.TestCase):
    def setUp(self):
        self.fmap, self.dump, self.rows = _rows()

    def test_universe_and_patched(self):
        self.assertEqual(len([r for r in self.rows if sl.matches(r, {'universe': 3})]), 4)
        self.assertEqual(len([r for r in self.rows if sl.matches(r, {'patched': False})]), 2)

    def test_text_filter_case_insensitive(self):
        layer = self.rows[0]['layer']
        n = len([r for r in self.rows if r['layer'] == layer])
        self.assertEqual(len([r for r in self.rows if sl.matches(r, {'layer': layer.upper()})]), n)

    def test_empty_string_matches_empty(self):
        self.assertEqual(len([r for r in self.rows if sl.matches(r, {'position': ''})]), 5)

    def test_sort_address(self):
        rows = sl.sort_rows(self.rows, 'address')
        keys = [(r['universe_number'], r['address']) for r in rows if r['patched']]
        self.assertEqual(keys, sorted(keys))
        self.assertFalse(rows[-1]['patched'])       # unpatched last

    def test_sort_position_units_numeric(self):
        rows = sl.sort_rows(self.rows, 'position')
        for a, b in zip(rows, rows[1:]):
            if a['position'] == b['position'] and a['unit_number'] and b['unit_number']:
                self.assertLessEqual(a['unit_number'], b['unit_number'])

    def test_bad_sort(self):
        with self.assertRaises(ValueError):
            sl.sort_rows(self.rows, 'nope')

    def test_select_fields_keeps_id(self):
        r = sl.select_fields(self.rows[0], ['unit'])
        self.assertEqual(set(r), {'unit', 'object_id'})


class NaturalSortTest(unittest.TestCase):
    def test_trek_order(self):
        # live test 2026-10-17: alphabetic order put Trek10..Trek51 before Trek6
        names = ['Trek10', 'Trek6', 'Trek51', 'Trek9', '', 'Trek40', 'FOH 1']
        got = [p['name'] for p in sl.sort_positions([{'name': n} for n in names])]
        self.assertEqual(got, ['FOH 1', 'Trek6', 'Trek9', 'Trek10', 'Trek40', 'Trek51', ''])

    def test_device_sort_by_natural_position(self):
        rows = [{'position': 'Trek10', 'unit_number': 1}, {'position': 'Trek6', 'unit_number': 2},
                {'position': 'Trek6', 'unit_number': 1}, {'position': None, 'unit_number': 1}]
        got = [(r['position'], r['unit_number']) for r in sl.sort_rows(rows, 'position')]
        self.assertEqual(got, [('Trek6', 1), ('Trek6', 2), ('Trek10', 1), (None, 1)])


class PositionLinkTest(unittest.TestCase):
    def test_link_by_name(self):
        _, _, rows = _rows()
        name = next(r['position'] for r in rows if r['position'])
        positions = [{'name': name}, {'name': 'empty pipe'}]
        links = sl.link_positions(positions, rows)
        self.assertEqual(positions[0]['device_count'],
                         len([r for r in rows if r['position'] == name]))
        self.assertEqual(positions[1]['device_count'], 0)
        self.assertEqual(links['devices_without_position'], 5)
        self.assertNotIn(name, links['device_positions_without_object'])


if __name__ == '__main__':
    unittest.main()
