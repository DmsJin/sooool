import json
from concurrent.futures import Future
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.scheduler import VirtualScheduler
from research.recover_prefix import durable_write
from research.run_episode import run


def answer(move):
    future = Future();future.set_result(f'[{move},1,1,0,12]')
    return future


class RaceSchedulerTests(unittest.TestCase):
    def test_first_valid_same_observation_locks_and_newer_can_replace(self):
        scheduler = VirtualScheduler(4, first_valid_per_observation=True)
        scheduler.submit(0, answer(99), 1)
        scheduler.submit(0, answer(3), 2)
        scheduler.submit(0, answer(7), 4)
        self.assertEqual(scheduler.advance(1)[0]['disposition'], 'invalid')
        self.assertEqual(scheduler.advance(2)[0]['disposition'], 'applied')
        self.assertEqual(scheduler.advance(4)[0]['disposition'], 'stale')
        self.assertEqual(scheduler.action_at(4)[0], 3)
        scheduler.submit(4, answer(1), 1)
        self.assertEqual(scheduler.advance(5)[0]['disposition'], 'applied')
        self.assertEqual(scheduler.action_at(5)[0], 1)

    def test_legacy_same_frame_replacement_unchanged(self):
        scheduler = VirtualScheduler(2)
        scheduler.submit(0, answer(3), 1)
        scheduler.submit(0, answer(7), 2)
        self.assertEqual(scheduler.advance(1)[0]['disposition'], 'applied')
        self.assertEqual(scheduler.advance(2)[0]['disposition'], 'applied')
        self.assertEqual(scheduler.action_at(2)[0], 7)

    def test_invalid_action_flag_does_not_claim_observation(self):
        scheduler = VirtualScheduler(2, first_valid_per_observation=True)
        invalid = Future();invalid.set_result({'answer': '[3,1,1,0,12]', 'invalid_action': True})
        scheduler.submit(0, invalid, 1)
        scheduler.submit(0, answer(7), 2)
        self.assertEqual(scheduler.advance(1)[0]['disposition'], 'invalid')
        self.assertEqual(scheduler.advance(2)[0]['disposition'], 'applied')


class RaceRunnerTests(unittest.TestCase):
    def test_complete_cohort_keeps_all_request_results_and_first_completion_wins(self):
        class Env:
            def __init__(self, *args, **kwargs): self.tick = 0;self.diags = 0
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def reset(self, *args, **kwargs): pass
            def clock(self):
                return {'frame': self.tick, 'visual_frame': self.tick, 'intro': 0, 'held': [0, 1, 1, 0], 'status': 'playing'}
            def diagnostics(self):
                self.diags += 1;self.tick += 1
                return {'state': {'status': 'lost' if self.diags >= 3 else 'playing', 'tick': self.tick,
                                  'hits': 0, 'score': 0, 'boss': {'hp': 1}, 'player': {'lives': 1, 'bombs': 1}},
                        'clock': self.clock()}
            def capture(self): return {'frame': self.tick, 'clock': self.clock(), 'png': b'png', 'held': [0, 1, 1, 0]}
            def apply(self, plan): return self.clock()

        class Pool:
            instances = []
            def __init__(self, *args): self.calls = [];self.closed = False;self.instances.append(self)
            def submit(self, prompt, images, directory):
                index = len(self.calls)
                # Each independent paid-client slot carries its own usage/cost.
                result = {'answer': f'[{3 if index == 0 else 7},1,1,0,12]',
                          'plan': [[3 if index == 0 else 7, 1, 1, 0, 12]],
                          'meta': {'request_id': str(index), 'usd': '0.1'},
                          'race_completed_ns': 200 if index == 0 else 100}
                durable_write(directory / 'result.json', result)
                self.calls.append((prompt, images, directory))
                future = Future();future.set_result(result)
                return future
            def close(self): self.closed = True

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);profile = root / 'profile.json';profile.write_text('{"samples_s":[1]}')
            config = {'profile': str(profile), 'url': 'unused', 'seed': 1, 'candidate': 'unused',
                      'provider': 'api', 'mode': 'realtime', 'decision_fanout': 2, 'workers': 2,
                      'capacity': 2, 'decision_stride': 10, 'image_stride': 10}
            out = root / 'episode'
            with patch('research.run_episode.BrowserEnv', Env), patch('research.run_episode.DecisionPool', Pool), patch('research.run_episode.make_prompt', return_value='Controller protocol: at most one request is in flight.'), patch('research.run_episode.time.sleep'):
                summary = run(config, out)
            self.assertEqual(summary['calls'], 2)
            rows = [json.loads(line) for line in (out / 'decisions.jsonl').read_text().splitlines()]
            actions = [json.loads(line) for line in (out / 'actions.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(sum(float(row['meta']['usd']) for row in rows), .2)
            self.assertEqual(actions[0]['plan'][0][0], 7)
            self.assertEqual(rows[0]['disposition'], 'stale')
            self.assertEqual(rows[1]['disposition'], 'applied')
            self.assertEqual(rows[0]['prompt_sha256'], rows[1]['prompt_sha256'])
            self.assertEqual(rows[0]['image_sha256'], rows[1]['image_sha256'])
            self.assertTrue(Pool.instances[-1].closed)
            self.assertNotIn('at most one request is in flight', Pool.instances[-1].calls[0][0])
            self.assertTrue(all((root / 'episode' / f'decision_{i:05d}/request.json').exists() for i in range(2)))

    def test_capacity_and_workers_must_fit_full_cohort(self):
        for overrides in ({'capacity': 1, 'workers': 2}, {'capacity': 2, 'workers': 1}):
            with self.assertRaisesRegex(ValueError, 'at least K'):
                run({'decision_fanout': 2, **overrides}, 'unused')


if __name__ == '__main__': unittest.main()
