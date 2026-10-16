"""Capture permitted player observations and verify a native match/replay."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('MUJOCO_GL', 'egl')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
from core.episode import load_plugin
from core.local import play, seat_spec
from core.sport import MatchConfig

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    plugin = str(ROOT / 'sports/tabletennis/plugin.py')
    sport = load_plugin(plugin)
    cfg = MatchConfig(sport='tabletennis', format='match', seats=('A',), seed=2,
                      level=1, slowdown=10, action_level='high')
    spec = seat_spec(sport, cfg, 'A', plugin=plugin)
    (args.output/'spec.json').write_text(json.dumps(spec, indent=2))
    from builtin_players import Reference
    ref = Reference(spec, 'A', 2)
    class Capture:
        count = 0
        captured = 0
        def act(self, view):
            self.count += 1
            if self.count % 4 == 1 and self.captured < 24:
                (args.output/f'sample_{self.captured:03d}.json').write_text(json.dumps(view))
                self.captured += 1
            return ref.act(view)
    player = Capture()
    result = play(sport, cfg, {'A': player}, data=args.output, plugin=plugin, every=5)
    print(json.dumps({'result': result, 'captured':player.captured}), flush=True)

if __name__ == '__main__':
    main()
