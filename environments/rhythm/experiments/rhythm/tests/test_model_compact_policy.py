import json
import unittest

from experiments.rhythm.model_compact_policy import INSTRUCTION, parse, prompt


class CompactPolicyTests(unittest.TestCase):
    def test_maps_wire_fields_and_preserves_literal_numbers(self):
        at, expiry = 12345.6789012345, 12346.987654321
        plan = parse(json.dumps({'v': 7, 'a': [['stable_1', 'j', at, expiry]]}))
        self.assertEqual(plan, {'version': 7, 'cancel_ids': [], 'replace_pending': False,
                               'taps': [{'id': 'stable_1', 'key': 'j', 'at_ms': at, 'expires_ms': expiry}]})
        self.assertEqual(plan['taps'][0]['at_ms'].hex(), at.hex())
        self.assertEqual(plan['taps'][0]['expires_ms'].hex(), expiry.hex())
        self.assertEqual(parse('{"v":0,"a":[]}')['taps'], [])

    def test_rejects_code_conditions_nonfinite_values_and_invalid_schema(self):
        invalid = [
            'setTimeout(()=>tap("d"),50)',
            '{"v":1,"a":[["a","d","now+20",1000]]}',
            '{"v":1,"a":[["a","d",1000,1100]],"if":"note-visible"}',
            '{"v":1,"a":[["a","d",NaN,1100]]}',
            '{"v":1,"a":[["a","d",1000,Infinity]]}',
            '{"v":1,"a":[["a","d",-1,1000]]}',
            '{"v":1,"a":[["a","d",1000,999]]}',
            '{"v":1,"a":[["a","d",true,1000]]}',
            '{"v":1,"a":[{"id":"a","key":"d","at_ms":1,"expires_ms":2}]}',
            '{"v":1,"a":[["a","d",1,2,3]]}',
            '{"v":-1,"a":[]}',
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse(value)

    def test_id_limits_uniqueness_and_finite_row_count(self):
        for identifier in ('bad id', 'x'*65, 'ü', ''):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                parse(json.dumps({'v': 1, 'a': [[identifier, 'd', 1, 2]]}))
        with self.assertRaises(ValueError):
            parse(json.dumps({'v': 1, 'a': [['a', 'd', 1, 2], ['a', 'f', 3, 4]]}))
        with self.assertRaises(ValueError):
            parse(json.dumps({'v': 1, 'a': [[str(i), 'd', 1, 2] for i in range(13)]}))

    def test_short_generic_instruction_retains_observation_whitelist(self):
        context = {'frames': [{'capture_start_ms': 10000, 'capture_end_ms': 10001,
                               'hidden_notes': 'PRIVATE_SENTINEL'}],
                   'external_now_ms': 10002, 'request_version': 3,
                   'model_memory': 'Model-authored strategy only.',
                   'chart': 'PRIVATE_SENTINEL'}
        text = prompt(context)
        self.assertLessEqual(len(INSTRUCTION), 500)
        self.assertNotIn('PRIVATE_SENTINEL', text)
        self.assertNotIn('hitline', text)
        self.assertNotIn('travel', text)
        self.assertIn('"request_version":3', text)


if __name__ == '__main__':
    unittest.main()
