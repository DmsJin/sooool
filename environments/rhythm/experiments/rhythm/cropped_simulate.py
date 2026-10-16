"""Cropped vision, sparse merging, measured delays and native-v2 timing policy."""
import argparse
import asyncio
import hashlib
import heapq
import json
import math
from pathlib import Path
import random
import time

from .cropped_policy import prompt, crop_observation
from .policy import parse
from .providers import NativeProvider
from .sparse_scheduler import SparseActionScheduler
from .visual_env import ROOT
from .visual_env_v2 import VisualRhythmEnv

RUNS = ROOT / 'experiments/rhythm/runs'


def apply_late_grace(actions, observation_ms, arrival_ms, grace_ms=55):
    """Drop old targets; press newly late targets NOW, never at a past time."""
    result = []
    for lane, relative in actions:
        if observation_ms + relative < arrival_ms - grace_ms:
            continue
        adjusted = max(relative, arrival_ms - observation_ms)
        if observation_ms + adjusted < arrival_ms:
            adjusted = math.nextafter(adjusted, math.inf)
        result.append([lane, adjusted])
    return result


async def episode(seed, rows, output, *, cadence=.10, capacity=20, workers=8, grace_ms=55):
    folder = output / f'pixels_cropped_v1-seed{seed}'
    folder.mkdir(exist_ok=False)
    providers = []
    free_workers = asyncio.Queue()
    pending = []
    rng = random.Random(seed)
    delays = [row['latency_s'] for row in rows]
    scheduler = SparseActionScheduler(commit_guard_ms=50)
    seq = calls = errors = drops = cursor = 0
    t, next_obs = 0., .45
    started = time.monotonic()

    async def infer(obs):
        provider = await free_workers.get()
        try:
            return await provider.act(prompt(obs), [obs.png])
        finally:
            free_workers.put_nowait(provider)

    async def synchronize(env):
        nonlocal cursor
        snapshot = await env.snapshot(cursor)
        for entry in snapshot['actions']:
            scheduler.acknowledge(entry['lane'], entry['time'] * 1000,
                                  entry['actual'] * 1000, executed=entry['status'] == 'executed')
        cursor = snapshot['cursor']

    try:
        for _ in range(workers):
            provider = await NativeProvider().start()
            providers.append(provider)
            free_workers.put_nowait(provider)
        async with VisualRhythmEnv('http://127.0.0.1:18891', virtual=True, late_grace_ms=grace_ms) as env:
            await env.start_virtual()
            while t < 30:
                await env.advance(t)
                await synchronize(env)
                changed = False
                while pending and pending[0][0] <= t + 1e-7:
                    due, rid, obs, future = heapq.heappop(pending)
                    log = {'seq': rid, 'obs_s': obs.time_s, 'arrival_s': t,
                           'sampled_delay_s': due - obs.time_s,
                           'image_sha256': hashlib.sha256(obs.png).hexdigest()}
                    try:
                        # Read the answer only at its sampled virtual arrival.
                        answer, metadata = await future
                        predicted = parse(answer, obs, 'pixels_cropped_v1')
                        actions = apply_late_grace(predicted, obs.time_s * 1000, t * 1000, grace_ms)
                        scheduler.submit(str(rid), obs.time_s * 1000, actions, t * 1000,
                                         horizon_ms=1800 + grace_ms, lanes=[0, 1, 2, 3])
                        log.update(answer=answer, metadata=metadata, predicted_actions=predicted, actions=actions)
                        changed = True
                    except Exception as error:
                        errors += 1
                        log['error'] = type(error).__name__ + ': ' + str(error)[:250]
                    with (folder / 'decisions.jsonl').open('a') as handle:
                        handle.write(json.dumps(log) + '\n')
                if changed:
                    await env.replace_schedule([{'time': action.game_ms / 1000, 'lane': action.lane}
                                                for action in scheduler.pending()], commit_guard_ms=50)
                    # Late-grace presses execute inside replacement at the current clock.
                    await synchronize(env)
                if t + 1e-7 >= next_obs:
                    if len(pending) < capacity:
                        obs = crop_observation(await env.screenshot())
                        (folder / f'obs-{seq:04d}.png').write_bytes(obs.png)
                        future = asyncio.create_task(infer(obs))
                        heapq.heappush(pending, (t + rng.choice(delays), seq, obs, future))
                        seq += 1
                        calls += 1
                    else:
                        drops += 1
                    next_obs += cadence
                    if calls % 10 == 0:
                        value = await env.evaluator()
                        progress = {'round': output.name, 'variant': 'pixels_cropped_v1', 'seed': seed,
                                    'game_s': t, 'calls': calls, 'score': value['score'],
                                    'counts': value['counts'], 'wall_s': time.monotonic() - started}
                        (folder / 'progress.json').write_text(json.dumps(progress))
                        print('CROPPED_SIM_PROGRESS ' + json.dumps(progress), flush=True)
                candidates = [30., next_obs]
                if pending:
                    candidates.append(pending[0][0])
                if scheduler.pending():
                    candidates.append(scheduler.pending()[0].game_ms / 1000)
                t = min(candidate for candidate in candidates if candidate > t + 1e-7)
            await env.advance(30.01)
            await synchronize(env)
            value = await env.evaluator()
            accuracy = value['score'] / max(1, value['total_notes'] * 1000)
            summary = {**value, 'accuracy': accuracy, 'passed': accuracy >= .95 and value['counts']['miss'] == 0,
                       'variant': 'pixels_cropped_v1', 'seed': seed, 'calls': calls, 'errors': errors,
                       'drops': drops, 'wall_s': time.monotonic() - started,
                       'mode': 'subscription_latency_simulation', 'speed': 1, 'cadence_s': cadence,
                       'virtual_capacity': capacity, 'real_workers': workers, 'late_grace_ms': grace_ms,
                       'commit_guard_ms': 50, 'sparse_match_window_ms': 100,
                       'request_profile_sha256': hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
            (folder / 'summary.json').write_text(json.dumps(summary, indent=2))
            (folder / 'actions.json').write_text(json.dumps(await env.action_log()))
            print('CROPPED_SIM_COMPLETE ' + json.dumps(summary), flush=True)
            return summary
    finally:
        for _, _, _, future in pending:
            future.cancel()
        await asyncio.gather(*(item[3] for item in pending), return_exceptions=True)
        await asyncio.gather(*(provider.close() for provider in providers), return_exceptions=True)


async def main(args):
    profile = Path(args.profile).resolve()
    data = json.loads(profile.read_text())
    if data.get('variant') != 'pixels_cropped_v1' or not data.get('serial'):
        raise ValueError('Requires explicit serial pixels_cropped_v1 profile')
    rows = data['rows']
    if len(rows) != 8 or any(row.get('status') != 'completed' or not row.get('parse_valid')
                             or row.get('model') != 'gpt-6.1-sol' or row.get('tier') != 'ultrafast'
                             or row.get('detail') != 'high' or row.get('effort') != 'low' for row in rows):
        raise ValueError('Requires eight completed valid high-detail/low-effort Sol Ultrafast samples')
    output = RUNS / args.round
    output.mkdir(exist_ok=False)
    files = ['experiments/rhythm/cropped_policy.py', 'experiments/rhythm/cropped_simulate.py',
             'experiments/rhythm/sparse_scheduler.py', 'experiments/rhythm/policy.py',
             'experiments/rhythm/scheduler.py', 'experiments/rhythm/providers.py',
             'experiments/rhythm/visual_env.py', 'experiments/rhythm/visual_env_v2.py',
             'dist/bridge-v2.js', 'dist/game.js']
    frozen = {'profile': str(profile), 'profile_sha256': hashlib.sha256(profile.read_bytes()).hexdigest(),
              'variant': 'pixels_cropped_v1', 'cadence_s': .10, 'capacity': 20, 'workers_per_episode': 8,
              'seeds': [2, 5, 6], 'commit_guard_ms': 50, 'late_grace_ms': 55, 'action_horizon_ms': 1855,
              'sparse_match_window_ms': 100, 'scheduler_mode': 'sparse_per_target_freshness_retaining_merge',
              'virtual_renderer': 'bridge_v2_pure_raf', 'speed': 1,
              'sources': {file: hashlib.sha256((ROOT / file).read_bytes()).hexdigest() for file in files}}
    (output / 'frozen.json').write_text(json.dumps(frozen, indent=2))
    results = await asyncio.gather(*(episode(seed, rows, output) for seed in [2, 5, 6]))
    if any(hashlib.sha256((ROOT / file).read_bytes()).hexdigest() != digest for file, digest in frozen['sources'].items()):
        raise RuntimeError('Frozen source changed during cropped simulation')
    (output / 'summary.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--round', default='r5-cropped')
    asyncio.run(main(parser.parse_args()))
