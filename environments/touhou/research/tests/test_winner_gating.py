import json
from concurrent.futures import Future
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.run_episode import run
from research.recover_prefix import durable_write


class WinnerGatingTests(unittest.TestCase):
    def simulate(self, invalid=False, terminal_frame=6, **overrides):
        class Env:
            def __init__(self, *args, **kwargs): self.frame = 0
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def reset(self, *args, **kwargs): pass
            def clock(self):
                return {'frame': self.frame, 'visual_frame': self.frame, 'intro': 0,
                        'held': [0, 1, 1, 0], 'pending_plan': [], 'status': 'playing'}
            def diagnostics(self):
                return {'clock': self.clock(), 'state': {'status': 'playing' if self.frame < terminal_frame else 'lost',
                        'tick': self.frame, 'hits': 0, 'score': 0, 'boss': {'hp': 1}, 'player': {'lives': 1, 'bombs': 1}}}
            def capture(self): return {'frame': self.frame, 'clock': self.clock(), 'png': b'png', 'held': [0, 1, 1, 0]}
            def advance(self, n): self.frame += n
            def apply(self, plan): return self.clock()

        class Pool:
            def __init__(self, *args): pass
            def submit(self, prompt, images, directory):
                result = {'answer': '[0,1,1,0,1]', 'plan': [[0, 1, 1, 0, 1]], 'meta': {}}
                if invalid:result.update(answer='invalid JSON',plan=None,invalid_action=True)
                durable_write(directory / 'result.json', result)
                future = Future();future.set_result(result)
                return future
            def close(self): pass

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);profile = root / 'profile.json';profile.write_text('{"samples_s":[1]}')
            config = {'profile': str(profile), 'url': 'unused', 'seed': 1, 'candidate': 'unused',
                      'provider': 'subscription', 'mode': 'sim', 'decision_fanout': 2, 'workers': 2,
                      'capacity': 4, 'decision_stride': 1, 'image_stride': 1, 'wait_for_move': True, **overrides}
            out = root / 'episode'
            with patch('research.run_episode.BrowserEnv', Env), patch('research.run_episode.DecisionPool', Pool), patch('research.run_episode.make_prompt', return_value='existing prompt'), patch('research.run_episode.sample_delay', side_effect=[5, 10, 5, 10, 5, 10]) as sampler:
                run(config, out)
                count = sampler.call_count
            requests = [json.loads(line) for line in (out / 'issued.jsonl').read_text().splitlines()]
            actions = [json.loads(line) for line in (out / 'actions.jsonl').read_text().splitlines()]
            prompts = [(out / f'decision_{i:05d}/prompt.txt').read_text() for i in range(len(requests))]
            return requests, actions, prompts, count

    def test_gate_prevents_second_cohort_before_winner_but_allows_stale_tail(self):
        rows, actions, prompts, count = self.simulate(wait_for_winner=True)
        self.assertEqual([row['visual_frame'] for row in rows], [0, 0, 5, 5])
        self.assertEqual(actions[0]['visual_frame'], 5)
        # The first cohort's slow candidate is still pending until frame10.
        self.assertEqual(rows[1]['delay_frames'], 10)
        self.assertEqual(rows[2]['visual_frame'], 5)
        self.assertIn('Winner-gated observations', prompts[0])

    def test_default_preserves_unwon_cohort_pipeline(self):
        rows, actions, prompts, count = self.simulate()
        self.assertEqual([row['visual_frame'] for row in rows], [0, 0, 1, 1])
        self.assertNotIn('Winner-gated observations', prompts[0])
        self.assertNotIn('Delay simulation:', prompts[0])

    def test_shared_delay_draws_once_per_cohort(self):
        rows, actions, prompts, count = self.simulate(wait_for_winner=True, cohort_delay='shared')
        self.assertEqual([row['delay_frames'] for row in rows], [5, 5, 10, 10])
        self.assertEqual(count, 2)
        self.assertTrue(all(row['cohort_delay'] == 'shared' for row in rows))
        self.assertIn('not calibrated concurrent API performance', prompts[0])

    def test_all_invalid_retries_only_after_last_virtual_due(self):
        # Native Futures are all already done at submission. Neither that fact
        # nor the first invalid due event at frame5 may release the gate.
        rows, actions, prompts, count = self.simulate(wait_for_winner=True, invalid=True, terminal_frame=11)
        self.assertEqual([row['visual_frame'] for row in rows], [0, 0, 10, 10])
        self.assertEqual(actions, [])
        self.assertIn('all candidates in that cohort have finished invalid', prompts[0])

    def test_invalid_delay_mode_fails_before_start(self):
        with self.assertRaisesRegex(ValueError, 'cohort_delay'):
            run({'cohort_delay': 'unrecognized'}, 'unused')


if __name__ == '__main__': unittest.main()
