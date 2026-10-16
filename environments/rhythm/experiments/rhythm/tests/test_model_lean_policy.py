import json
import unittest

from experiments.rhythm.model_lean_policy import INSTRUCTION, parse, prompt


class LeanPolicyTests(unittest.TestCase):
    def observation(self):
        return {'frames': [{'capture_start_ms': 10001.123, 'capture_end_ms': 10002.456,
                            'private_notes': 'PRIVATE_SENTINEL'}],
                'external_now_ms': 10003.789, 'request_version': 9, 'queue_version': 8,
                'pending_plans': [{'id': 'tap_a', 'key': 'f', 'at_ms': 12345.6789012345,
                                   'expires_ms': 12400.987654321, 'admitted_version': 8,
                                   'hidden_chart': 'PRIVATE_SENTINEL'}],
                'executed_acks': [{'id': str(i), 'status': 'executed' if i % 2 else 'rejected',
                                   'key': 'j', 'at_ms': 11000.123 + i, 'actual_ms': 11000.456 + i,
                                   'private_notes': 'PRIVATE_SENTINEL', 'version': i} for i in range(4)],
                'rtt_history_ms': [1000.123, 1100.456, 1200.789, 1300.012, 1400.345],
                'model_memory': 'Model-authored guidance.', 'game_state': 'PRIVATE_SENTINEL'}

    def test_codec_projects_raw_metadata_without_timing_computation(self):
        observation = self.observation()
        text = prompt(observation)
        context = json.loads(text.rsplit('\n', 1)[1])
        self.assertEqual(set(context), {'f', 'now', 'p', 'ack', 'rtt', 'v'})
        self.assertEqual(context['f'], [[10001.123, 10002.456]])
        self.assertEqual(context['now'], observation['external_now_ms'])
        self.assertEqual(context['p'], [['tap_a', 'f', 12345.6789012345, 12400.987654321]])
        self.assertEqual(context['ack'], [{key: item[key] for key in ('id', 'status', 'key', 'at_ms', 'actual_ms')}
                                          for item in observation['executed_acks'][-2:]])
        self.assertEqual(context['ack'][0]['status'], 'rejected')  # No status filtering.
        self.assertEqual(context['rtt'], observation['rtt_history_ms'][-4:])
        self.assertEqual(context['v'], 9)
        self.assertLess(text.index(observation['model_memory']), text.index('OBSERVATION:'))
        self.assertNotIn('queue_version', text)
        self.assertNotIn('PRIVATE_SENTINEL', text)
        self.assertLessEqual(len(INSTRUCTION), 450)

    def test_parser_remains_finite_and_preserves_literal_output_numbers(self):
        at, expiry = 12345.6789012345, 12400.987654321
        plan = parse(json.dumps({'v': 9, 'a': [['tap_a', 'f', at, expiry]]}))
        self.assertEqual(plan['taps'][0]['at_ms'].hex(), at.hex())
        self.assertEqual(plan['taps'][0]['expires_ms'].hex(), expiry.hex())
        self.assertFalse(plan['replace_pending'])
        with self.assertRaises(ValueError):
            parse('{"v":9,"a":[["tap_a","f",NaN,12400]]}')

    def test_latency_ablation_removes_rtt_without_changing_other_observations(self):
        observation=self.observation()
        normal=json.loads(prompt(observation).rsplit('\n',1)[1])
        blind=prompt(observation,include_rtt=False)
        expected={key:value for key,value in normal.items() if key!='rtt'}
        self.assertEqual(json.loads(blind.rsplit('\n',1)[1]),expected)
        self.assertNotIn('rtt=',blind)
        for value in observation['rtt_history_ms']:
            self.assertNotIn(str(value),blind)


if __name__ == '__main__':
    unittest.main()
