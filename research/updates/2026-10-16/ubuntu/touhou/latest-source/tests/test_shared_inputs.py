import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.api_client import ApiClient
from research.budget import BudgetLedger
from research.recover_prefix import recover_prefix
from research.run_episode import DecisionPool, run
from research.tests.test_api_schema import MockSession


class SharedInputTests(unittest.TestCase):
    def test_hardlinks_preserve_hashes_independent_accounting_and_early_submit(self):
        png = b'\x89PNG\r\n\x1a\n' + b'\0' * 8 + (640).to_bytes(4, 'big') + (480).to_bytes(4, 'big')
        class Env:
            def __init__(self, *args, **kwargs): self.frame = 0
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def reset(self, *args, **kwargs): pass
            def clock(self): return {'frame': self.frame, 'visual_frame': self.frame, 'intro': 0, 'held': [0, 1, 1, 0]}
            def diagnostics(self):
                return {'clock': self.clock(), 'state': {'status': 'playing' if self.frame < 3 else 'lost', 'tick': self.frame,
                        'hits': 0, 'score': 0, 'boss': {'hp': 1}, 'player': {'lives': 1, 'bombs': 1}}}
            def capture(self): return {'frame': self.frame, 'clock': self.clock(), 'png': png, 'held': [0, 1, 1, 0]}
            def advance(self, n): self.frame += n
            def apply(self, plan): return self.clock()

        original_submit = DecisionPool.submit
        submits = []
        def checked_submit(pool, prompt, images, directory):
            # Each manifest and issue is durable before dispatch; first dispatch
            # is not held until the rest of the cohort has been prepared.
            self.assertTrue((directory / 'request.json').exists())
            issued = [json.loads(line) for line in (pool.out / 'issued.jsonl').read_text().splitlines()]
            self.assertEqual(len(issued), len(submits) + 1)
            if not submits:self.assertFalse((pool.out / 'decision_00001').exists())
            submits.append(directory)
            return original_submit(pool, prompt, images, directory)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);profile = root / 'profile.json';profile.write_text('{"samples_s":[0.01]}')
            ledger = root / 'budget.json';out = root / 'episode'
            config = {'profile': str(profile), 'url': 'unused', 'seed': 1, 'candidate': 'unused',
                      'provider': 'api', 'mode': 'sim', 'decision_fanout': 2, 'workers': 2, 'capacity': 2,
                      'decision_stride': 10, 'image_stride': 10, 'shared_cohort_inputs': True, 'ledger': str(ledger)}
            with patch('research.run_episode.BrowserEnv', Env), patch('research.run_episode.make_prompt', return_value='observe'), patch.object(DecisionPool, 'submit', checked_submit), patch('requests.Session', side_effect=lambda: MockSession()):
                summary = run(config, out, key='offline-mock-key')
            self.assertEqual(summary['calls'], 2)
            first, second = out / 'decision_00000', out / 'decision_00001'
            for name in ('prompt.txt', 'image_0.png'):
                self.assertEqual(os.stat(first / name).st_ino, os.stat(second / name).st_ino)
                self.assertEqual(os.stat(first / name).st_mode & 0o777, 0o444)
            for name in ('request.json', 'result.json'):
                self.assertNotEqual(os.stat(first / name).st_ino, os.stat(second / name).st_ino)
            rows = [json.loads(line) for line in (out / 'decisions.jsonl').read_text().splitlines()]
            self.assertEqual(len(recover_prefix(out)), 2)
            self.assertEqual(rows[0]['image_sha256'], rows[1]['image_sha256'])
            self.assertNotEqual(rows[0]['meta']['request_id'], rows[1]['meta']['request_id'])
            accounting = BudgetLedger(ledger).snapshot()
            self.assertEqual(len(accounting['requests']), 2)
            self.assertTrue(all(row['status'] == 'settled' for row in accounting['requests'].values()))
            self.assertEqual(sum(float(row['meta']['usd']) for row in rows), float(accounting['committed_usd']))
            for row in rows:
                stage = row['stage_timing'];api = row['meta']['stage_timing']
                self.assertLessEqual(stage['capture_completed_wall_s'], stage['inputs_durable_wall_s'])
                self.assertLessEqual(stage['manifest_durable_wall_s'], stage['future_submit_started_wall_s'])
                self.assertLessEqual(stage['issued_durable_wall_s'], stage['future_submit_started_wall_s'])
                self.assertLessEqual(stage['future_submit_started_wall_s'], api['worker_started_wall_s'])
                self.assertLessEqual(api['api_prepare_started_wall_s'], api['network_started_wall_s'])
                self.assertLessEqual(api['network_started_wall_s'], api['network_completed_wall_s'])
                self.assertLessEqual(api['network_completed_wall_s'], api['usage_settled_wall_s'])
                self.assertLessEqual(api['result_write_started_wall_s'], api['result_durable_wall_s'])

    def test_default_api_metadata_has_no_stage_instrumentation(self):
        with tempfile.TemporaryDirectory() as temp:
            png = b'\x89PNG\r\n\x1a\n' + b'\0' * 8 + (640).to_bytes(4, 'big') + (480).to_bytes(4, 'big')
            result = ApiClient('offline-mock-key', Path(temp) / 'ledger.json', session=MockSession()).decide('observe', [png])
            self.assertNotIn('stage_timing', result['meta'])


if __name__ == '__main__': unittest.main()
