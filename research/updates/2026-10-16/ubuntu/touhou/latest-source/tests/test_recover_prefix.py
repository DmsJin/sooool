import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research.recover_prefix import recover_prefix, durable_write


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'issued.jsonl').touch()

    def tearDown(self):
        self.temp.cleanup()

    def decision(self, seq, complete=True):
        directory = self.root / f'decision_{seq:05d}'
        directory.mkdir()
        prompt, png = f'Observe {seq}'.encode(), b'example-png-' + bytes([seq])
        (directory / 'prompt.txt').write_bytes(prompt)
        (directory / 'image_0.png').write_bytes(png)
        request = {'seq': seq, 'visual_frame': 100 + seq * 15, 'logical_frame': seq * 15,
                   'image_frames': [seq * 15], 'image_sha256': [hashlib.sha256(png).hexdigest()],
                   'prompt_sha256': hashlib.sha256(prompt).hexdigest(), 'held': [0, 1, 1, 0],
                   'delay_frames': 30, 'submitted_wall_s': float(seq)}
        durable_write(directory / 'request.json', request)
        if complete:
            durable_write(directory / 'result.json', {'answer': '[[0,1,1,0,12]]', 'plan': [[0, 1, 1, 0, 12]], 'meta': {}})
        return directory

    def test_gap_never_uses_later_answers(self):
        self.decision(0)
        self.decision(1, complete=False)
        self.decision(2)
        self.assertEqual([r['seq'] for r in recover_prefix(self.root)], [0])

    def test_prompt_corruption_rejected(self):
        decision = self.decision(0)
        (decision / 'prompt.txt').write_text('different prompt')
        with self.assertRaisesRegex(ValueError, 'prompt hash mismatch'):
            recover_prefix(self.root)

    def test_png_corruption_rejected(self):
        decision = self.decision(0)
        (decision / 'image_0.png').write_bytes(b'different image')
        with self.assertRaisesRegex(ValueError, 'image 0 hash mismatch'):
            recover_prefix(self.root)

    def test_crash_before_issue_stops_cleanly(self):
        self.decision(0)
        (self.root / 'decision_00001').mkdir()
        self.assertEqual(len(recover_prefix(self.root)), 1)

    def test_legacy_timing_not_invented(self):
        self.decision(0)
        (self.root / 'issued.jsonl').unlink()
        (self.root / 'decision_00000' / 'request.json').unlink()
        with self.assertRaisesRegex(ValueError, 'legacy run'):
            recover_prefix(self.root)

    def test_result_cannot_replace_observation_time(self):
        decision = self.decision(0)
        result = json.loads((decision / 'result.json').read_text())
        result['visual_frame'] = 9999
        durable_write(decision / 'result.json', result)
        with self.assertRaisesRegex(ValueError, 'overwrites request manifest'):
            recover_prefix(self.root)


if __name__ == '__main__':
    unittest.main()

class RunnerDurabilityTests(unittest.TestCase):
    def test_issue_is_durable_before_submit_and_actions_are_logged(self):
        from concurrent.futures import Future
        from unittest.mock import patch
        from research.run_episode import run

        class FakeEnv:
            def __init__(self, *args, **kwargs): self.tick = 0
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def reset(self, *args, **kwargs): pass
            def diagnostics(self):
                return {'state': {'status': 'playing' if self.tick < 5 else 'lost', 'tick': self.tick,
                                  'hits': 0, 'score': 0, 'boss': {'hp': 100}, 'player': {'lives': 1, 'bombs': 1}},
                        'clock': {'visual_frame': self.tick, 'frame': self.tick, 'intro': 0, 'held': [0, 1, 1, 0]}}
            def capture(self): return {'frame': self.tick, 'png': b'png', 'held': [0, 1, 1, 0]}
            def advance(self, count): self.tick += count
            def apply(self, plan): return self.diagnostics()['clock']

        class FakePool:
            def __init__(self, config, out, key): self.out = out
            def submit(self, prompt, images, directory):
                request = json.loads((directory / 'request.json').read_text())
                issued = [json.loads(line) for line in (self.out / 'issued.jsonl').read_text().splitlines()]
                assert issued[-1]['seq'] == request['seq']
                assert issued[-1]['prompt_sha256'] == hashlib.sha256(prompt.encode()).hexdigest()
                result = {'answer': '[[0,1,1,0,12]]', 'plan': [[0, 1, 1, 0, 12]], 'meta': {}}
                durable_write(directory / 'result.json', result)
                future = Future();future.set_result(result)
                return future
            def close(self): pass

        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            profile = directory / 'profile.json';profile.write_text('{"samples_s":[0.02]}')
            out = directory / 'episode'
            config = {'profile': str(profile), 'url': 'unused', 'seed': 1, 'candidate': 'unused',
                      'provider': 'subscription', 'mode': 'sim', 'decision_stride': 1, 'image_stride': 1}
            with patch('research.run_episode.BrowserEnv', FakeEnv), patch('research.run_episode.DecisionPool', FakePool), patch('research.run_episode.make_prompt', return_value='observe'):
                run(config, out)
            issued = [json.loads(line) for line in (out / 'issued.jsonl').read_text().splitlines()]
            prefix = [json.loads(line) for line in (out / 'completed_prefix.jsonl').read_text().splitlines()]
            actions = [json.loads(line) for line in (out / 'actions.jsonl').read_text().splitlines()]
            self.assertEqual(len(prefix), len(issued))
            self.assertGreater(len(actions), 0)
            self.assertEqual(actions, json.loads((out / 'actions.json').read_text()))
            self.assertEqual(len(recover_prefix(out)), len(issued))
