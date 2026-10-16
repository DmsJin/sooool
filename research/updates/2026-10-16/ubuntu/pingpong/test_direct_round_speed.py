"""Check the scheduler really forwards S2/S1; no games or model calls."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import run_round


class SpeedRouting(unittest.TestCase):
    def test_per_job_speed_overrides_round_speed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = root / 'plan.json'
            plan.write_text(json.dumps({'profile': 'fixture', 'parallel_episodes': 2,
                'workers_per_episode': 3, 'slowdown': 2, 'stride': 5,
                'jobs': [{'name': 'S2', 'seed': 1, 'variant': 'direct_v1'},
                         {'name': 'S1', 'seed': 2, 'variant': 'direct_v1', 'slowdown': 1}]}))
            captured = []
            class Process:
                pid = 12345
                def __init__(self, command, **kwargs):
                    captured.append(command)
                    out = Path(command[command.index('--output') + 1])
                    out.mkdir()
                    (out / 'summary.json').write_text(json.dumps({'finished': False, 'screened': True, 'failure': None}))
                def wait(self):
                    return 0
            with patch.object(run_round.subprocess, 'Popen', Process):
                run_round.run(SimpleNamespace(plan=plan, output=root / 'round', python='fixture-python'))
            speeds = {int(c[c.index('--seed') + 1]): float(c[c.index('--slowdown') + 1]) for c in captured}
            self.assertEqual(speeds, {1: 2, 2: 1})
            self.assertTrue(all(c[c.index('--stride') + 1] == '5' for c in captured))


if __name__ == '__main__':
    unittest.main()
