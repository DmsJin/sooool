"""Separate sparse-policy simulation using an explicitly supplied API profile."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from . import simulate_candidate
from .sparse_policy import prompt
from .sparse_scheduler import SparseActionScheduler
from .visual_env import ROOT


async def main(args):
    profile = Path(args.profile).resolve()
    data = json.loads(profile.read_text())
    if data.get('variant') != 'pixels_sparse' or not data.get('serial'):
        raise ValueError('Requires an explicitly supplied serial pixels_sparse profile')
    rows = data['rows']
    if len(rows) != 8 or any(row.get('status') != 'completed' or not row.get('parse_valid')
                             or row.get('model') != 'gpt-6.1-sol' or row.get('tier') != 'ultrafast'
                             or row.get('detail') != 'high' or row.get('effort') != 'low' for row in rows):
        raise ValueError('Requires eight completed valid high-detail/low-effort Sol Ultrafast samples')
    output = simulate_candidate.RUNS / args.round
    output.mkdir(exist_ok=False)
    files = ['experiments/rhythm/sparse_policy.py', 'experiments/rhythm/sparse_simulate.py',
             'experiments/rhythm/sparse_scheduler.py',
             'experiments/rhythm/simulate_candidate.py', 'experiments/rhythm/policy.py',
             'experiments/rhythm/scheduler.py', 'experiments/rhythm/providers.py',
             'experiments/rhythm/visual_env.py', 'dist/agent-bridge.js', 'dist/game.js']
    frozen = {'profile': str(profile), 'profile_sha256': hashlib.sha256(profile.read_bytes()).hexdigest(),
              'variant': 'pixels_sparse', 'cadence_s': .30, 'capacity': 8,
              'workers_per_episode': 8, 'seeds': [2, 5, 6], 'commit_guard_ms': 50,
              'sparse_match_window_ms': 100, 'scheduler_mode': 'sparse_retaining_merge',
              'sources': {file: hashlib.sha256((ROOT / file).read_bytes()).hexdigest() for file in files}}
    (output / 'frozen.json').write_text(json.dumps(frozen, indent=2))
    # Process-local patch only. No frozen source or other running process changes.
    simulate_candidate.prompt = prompt
    simulate_candidate.ActionScheduler = SparseActionScheduler
    results = await asyncio.gather(*(simulate_candidate.episode('pixels_sparse', seed, rows,
                cadence=.30, workers=8, capacity=8, round_name=args.round, commit_guard_ms=50)
                for seed in [2, 5, 6]))
    if any(hashlib.sha256((ROOT / file).read_bytes()).hexdigest() != digest for file, digest in frozen['sources'].items()):
        raise RuntimeError('Source changed during sparse simulation')
    (output / 'summary.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--round', default='r4-sparse')
    asyncio.run(main(parser.parse_args()))
