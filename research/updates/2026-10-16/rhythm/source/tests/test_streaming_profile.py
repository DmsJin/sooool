import json
from pathlib import Path
import tempfile
import unittest
from experiments.rhythm.model_joint_profile import extract


class StreamingProfileTests(unittest.TestCase):
    def test_action_delivery_and_capacity_are_distinct_and_legacy_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);rows=[]
            base={'version':1,'observation':{'external_now_ms':10000},
                'frame_metadata':[{'capture_end_ms':9980}],'receipt':{'clock_ms':10150}}
            rows.append({**base,'metadata':{'latency_s':.1}})
            rows.append({**base,'version':2,'action_delivery':{'action_ready_s':.1},
                'metadata':{'latency_s':1.1,'total_provider_s':1.15,'pre_http_s':.02,'action_callback_s':.01}})
            (p/'requests.jsonl').write_text('\n'.join(map(json.dumps,rows)))
            profile=extract(p/'requests.jsonl',p/'profile.json')
            old,new=profile['rows']
            self.assertAlmostEqual(old['api_rtt_s'],.1)
            self.assertAlmostEqual(old['transport_overhead_s'],.05)
            self.assertAlmostEqual(old['request_occupancy_s'],.15)
            self.assertAlmostEqual(new['api_rtt_s'],.1)
            self.assertAlmostEqual(new['transport_overhead_s'],.05)
            self.assertAlmostEqual(new['request_occupancy_s'],1.17)
            self.assertAlmostEqual(new['completion_rtt_s'],1.1)

    def test_unknown_tail_cannot_be_silently_resampled_as_a_short_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            row={'version':1,'observation':{'external_now_ms':10000},
                'frame_metadata':[{'capture_end_ms':9980}],'receipt':{'clock_ms':10150},
                'action_delivery':{'action_ready_s':.1},'error':'Late stream loss'}
            (p/'requests.jsonl').write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError,'unknown request occupancy'):
                extract(p/'requests.jsonl',p/'profile.json')
            self.assertFalse((p/'profile.json').exists())
