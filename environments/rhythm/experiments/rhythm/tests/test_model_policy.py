import json
import unittest

from experiments.rhythm.model_policy import parse, prompt
from experiments.rhythm.model_profile import observation_context


class ModelPolicyTests(unittest.TestCase):
    def plan(self):
        return {'version': 7, 'cancel_ids': ['obsolete'],
                'taps': [{'id': 'a', 'key': 'd', 'at_ms': 100123.4567, 'expires_ms': 100210.9876}]}

    def test_parser_preserves_literal_numbers_without_timing_correction(self):
        data = self.plan()
        # Validation may reject invalid data but never clamps, rewinds, predicts,
        # converts, or otherwise changes valid model numbers.
        self.assertEqual(parse(json.dumps(data)), data)
        for at, expiry in ((-1, 20), (30, 20), (-30, -20)):
            data = self.plan()
            data['taps'][0].update(at_ms=at, expires_ms=expiry)
            with self.assertRaises(ValueError):
                parse(json.dumps(data))

    def test_schema_rejects_nonfinite_bool_extra_fields_and_bad_keys(self):
        for field, value in [('at_ms', float('nan')), ('expires_ms', float('inf')),
                             ('at_ms', True), ('key', 'x'), ('key', []), ('id', '')]:
            with self.subTest(field=field, value=value):
                data = self.plan()
                data['taps'][0][field] = value
                with self.assertRaises(ValueError):
                    parse(json.dumps(data))
        data = self.plan()
        data['notes'] = [{'lane': 0, 'time': 7}]
        with self.assertRaises(ValueError):
            parse(json.dumps(data))

    def test_finite_plan_size_and_unique_tap_ids(self):
        data = self.plan()
        data['taps'] *= 2
        with self.assertRaises(ValueError):
            parse(json.dumps(data))

    def test_executor_identifier_cancel_and_safe_version_constraints(self):
        for identifier in ('bad id', 'bad.id', 'x' * 65, 'ü'):
            data = self.plan()
            data['taps'][0]['id'] = identifier
            with self.assertRaises(ValueError):
                parse(json.dumps(data))
        for cancels in (['a', 'a'], [str(i) for i in range(13)], ['bad id']):
            data = self.plan()
            data['cancel_ids'] = cancels
            with self.assertRaises(ValueError):
                parse(json.dumps(data))
        for version in (-1, 2**53, 1.5, True):
            data = self.plan()
            data['version'] = version
            with self.assertRaises(ValueError):
                parse(json.dumps(data))
        data = self.plan()
        data['version'] = 2**53 - 1
        self.assertEqual(parse(json.dumps(data)), data)
        data = self.plan()
        data['taps'] = [{'id': str(i), 'key': 'f', 'at_ms': i, 'expires_ms': i} for i in range(13)]
        with self.assertRaises(ValueError):
            parse(json.dumps(data))

    def test_optional_replace_pending_boolean_and_raw_snapshot_aliases(self):
        data = self.plan()
        self.assertFalse(parse(json.dumps(data)).get('replace_pending', False))
        data['replace_pending'] = True
        self.assertEqual(parse(json.dumps(data)), data)
        data['replace_pending'] = 1
        with self.assertRaises(ValueError):
            parse(json.dumps(data))
        pending = [{'id': 'old', 'key': 'd', 'at_ms': 100010, 'expires_ms': 100020}]
        acknowledgements = [{'id': 'a', 'status': 'executed', 'actual_ms': 100000}]
        context = observation_context([], {'clock_ms': 100001, 'version': 4,
                                          'pending': pending, 'rawacks': acknowledgements}, request_version=5)
        self.assertIs(context['pending_plans'], pending)
        self.assertIs(context['executed_acks'], acknowledgements)
        self.assertEqual(context['queue_version'], 4)

    def test_prompt_excludes_chart_game_geometry_and_frame_private_fields(self):
        frames = [{'png': b'not serialized', 'capture_start_ms': 100000,
                   'capture_end_ms': 100001, 'hidden_notes': 'SECRET_NOTE_SENTINEL'}]
        observation = observation_context(frames, {'clock_ms': 100002, 'queue_version': 4,
                                                   'chart': 'SECRET_CHART_SENTINEL'}, request_version=3)
        observation.update(geometry={'hitline_y': 'SECRET_GEOMETRY_SENTINEL'},
                           game_time=123, hidden_chart='SECRET_CHART_SENTINEL')
        text = prompt(observation)
        for forbidden in ('SECRET_NOTE_SENTINEL', 'SECRET_CHART_SENTINEL', 'SECRET_GEOMETRY_SENTINEL',
                          'hitline', 'travel', '1800', '55ms', 'game_time'):
            self.assertNotIn(forbidden, text)
        self.assertIn('100002', text)
        self.assertIn('"request_version":3', text)
        self.assertIn('"queue_version":4', text)


if __name__ == '__main__':
    unittest.main()
