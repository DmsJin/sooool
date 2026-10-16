import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import Future
from unittest.mock import patch

from research.recover_prefix import durable_write
from research.run_episode import run, timing_clock


class RealtimeAuditTests(unittest.TestCase):
    def test_clock_evidence_excludes_keys_and_hidden_state(self):
        self.assertEqual(timing_clock({'frame': 3, 'visual_frame': 5, 'wall_ms': 80,
                                       'held': [1], 'player': {'x': 123}}),
                         {'frame': 3, 'visual_frame': 5, 'wall_ms': 80})

    def test_capture_and_apply_frames_are_actual_browser_frames(self):
        class Env:
            def __init__(self, *args, **kwargs): self.tick = 0
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def reset(self, *args, **kwargs): pass
            def clock(self):
                return {'frame': self.tick, 'visual_frame': self.tick, 'intro': 0,
                        'held': [0, 1, 1, 0], 'wall_ms': self.tick * 1000 / 60,
                        'mode': 'realtime', 'speed': 1, 'actual_visual_speed': 1,
                        'max_raf_gap_ms': 20, 'blur_events': 0, 'paused': False,
                        'status': 'lost' if self.tick >= 7 else 'playing'}
            def diagnostics(self):
                return {'state': {'status': self.clock()['status'], 'tick': self.tick,
                                  'hits': 0, 'score': 0, 'boss': {'hp': 1},
                                  'player': {'lives': 1, 'bombs': 1}}, 'clock': self.clock()}
            def capture(self):
                self.tick += 3
                return {'frame': self.tick, 'clock': self.clock(), 'png': b'png', 'held': [0, 1, 1, 0]}
            def apply(self, plan):
                self.tick += 4
                return self.clock()

        class Pool:
            def __init__(self, *args): pass
            def submit(self, prompt, images, directory):
                result = {'answer': '[[0,1,1,0,12]]', 'plan': [[0, 1, 1, 0, 12]], 'meta': {}}
                durable_write(directory / 'result.json', result)
                future = Future();future.set_result(result)
                return future
            def close(self): pass

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = root / 'profile.json';profile.write_text('{"samples_s":[1]}')
            config = {'profile': str(profile), 'url': 'unused', 'seed': 1, 'candidate': 'unused',
                      'provider': 'api', 'mode': 'realtime', 'decision_stride': 1, 'image_stride': 1}
            out = root / 'episode'
            with patch('research.run_episode.BrowserEnv', Env), patch('research.run_episode.DecisionPool', Pool), patch('research.run_episode.make_prompt', return_value='same prompt'), patch('research.run_episode.time.sleep'):
                run(config, out)
            request = json.loads((out / 'decision_00000/request.json').read_text())
            action = json.loads((out / 'actions.jsonl').read_text().splitlines()[0])
            self.assertEqual(request['visual_frame'], 3)
            self.assertEqual(request['logical_frame'], 3)
            self.assertEqual(request['capture_clock']['visual_frame'], 3)
            self.assertEqual(action['visual_frame'], 7)
            self.assertEqual(action['logical_frame'], 7)
            self.assertEqual(action['apply_clock']['wall_ms'], 7 * 1000 / 60)
            self.assertEqual(action['age_frames'], 4)


if __name__ == '__main__': unittest.main()
