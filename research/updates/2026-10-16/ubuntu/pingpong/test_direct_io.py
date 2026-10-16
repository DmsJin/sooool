import json
import unittest

from direct_io import parse, prompt


ACT = {'type': 'act', 't': .7, 'pos': [0, -1.4, .2],
       'normal': [0, 1, 0], 'vel': [0, 2, 0]}


class DirectIOTests(unittest.TestCase):
    def test_supported_actions_exact(self):
        for obj in ({'type': 'wait'}, {'type': 'none'},
                    {'type': 'move', 'base': [-1, -2.4]},
                    {'type': 'toss', 'pos': [0, -1.5, .3], 'height': .16},
                    ACT, {**ACT, 'base': [1, -1.5]}):
            self.assertEqual(parse(json.dumps(obj)), obj)

    def test_invalid_json_and_types(self):
        for text in (None, b'{}', '', 'null', '[]', '{}', 'true',
                     '{"type":"wait","type":"none"}',
                     '{"type":"wait","x":{"a":0,"a":1}}',
                     '{"type":"wait"} trailing', '```{"type":"wait"}```',
                     '{"type":"act","t":NaN}', '{"type":"act","t":Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)

    def test_schema_and_numeric_bounds(self):
        bad = [{**ACT, 't': t} for t in (True, 0, -1, 2.5001, '1', None, float('nan'), float('inf'))]
        bad += [{**ACT, key: value} for key, value in (
            ('pos', [0, 0, 0]), ('pos', [2.1, -1, 0]), ('pos', [0, -1, 1.6]),
            ('normal', [0, 0, 0]), ('normal', [0, True, 0]),
            ('vel', [6, 6, 0]), ('vel', [0, 1e309, 0]), ('vel', [0, 0]),
            ('base', [0, -1.49]), ('base', None), ('extra', 1))]
        bad += [{'type': 'move'}, {'type': 'hit'}, {'type': 'none', 't': 1},
                {'type': 'wait', 'wait_steps': 2},
                {'type': 'toss', 'pos': [0, -1, .2], 'height': .2},
                {'type': 'toss', 'pos': [0, -1.5, .01], 'height': .2},
                {'type': 'toss', 'pos': [0, -1.5, .3], 'height': 1.1}]
        for obj in bad:
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                parse(json.dumps(obj))
        for key in ACT:
            with self.subTest(missing=key), self.assertRaises(ValueError):
                parse(json.dumps({k: v for k, v in ACT.items() if k != key}))

    def test_native_boundaries_and_preservation(self):
        obj = {**ACT, 't': 2.5, 'pos': [-2, -3.3, -.5], 'vel': [8, 0, 0],
               'normal': [0, 2, 0], 'base': [1, -1.5]}
        self.assertEqual(parse(json.dumps(obj)), obj)
        obj['t'] = 1e-12
        self.assertEqual(parse(json.dumps(obj)), obj)

    def test_prompt_public_only_and_variants(self):
        feedback = {'step': 12, 'execution_feedback': {'blade_error_m': .1, 'private': 'SECRET'}}
        view = {'state': {'step': 10, 'q': [0]*9, 'ball_state': 'coming to you',
                          'stance_check': 'SECRET', 'fit': 'SECRET', 'candidates': 'SECRET',
                          'hidden_ball': 'SECRET', 'known_plan': 'SECRET', 'recent_applied': [feedback]},
                'observation': {'image_png_b64': 'SECRET', 'snaps': 'SECRET',
                                'wall_mono': 'SECRET', 'view_steps': [4, 6, 8, 10]}}
        spec = {'cameras': [{'name': 'behind'}], 'actions': {'act': {}}, 'private': 'SECRET'}
        for variant in ('direct_v1', 'direct_latency_v1', 'direct_feedback_v1'):
            text = prompt(view, spec, {'p50_game_s': .2, 'sampled_delay_s': 'SECRET'}, variant)
            self.assertNotIn('SECRET', text)
            self.assertIn('"view_steps":[4,6,8,10]', text)
            self.assertIn('"cameras":[{"name":"behind"}]', text)
            self.assertEqual('"blade_error_m":0.1' in text, variant == 'direct_feedback_v1')
        with self.assertRaises(ValueError):
            prompt(view, spec, variant='old_menu_policy')


if __name__ == '__main__':
    unittest.main()
