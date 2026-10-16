"""Recover interrupted r1 episodes by replaying their immutable causal prefix.

No API transport is used. --replay-only (default) validates without new model
calls. --live resumes missing decisions through subscription workers only.
"""
import argparse
import asyncio
import hashlib
import heapq
import importlib.util
import json
import pathlib
import random
import sys
import time

from .policy import parse, prompt
from .providers import NativeProvider
from .visual_env import Observation, VisualRhythmEnv

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNS = ROOT / 'experiments/rhythm/runs'


def baseline_scheduler():
    source = RUNS / 'r1/source/scheduler.py'
    spec = importlib.util.spec_from_file_location('_rhythm_r1_archived_scheduler', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.ActionScheduler(), hashlib.sha256(source.read_bytes()).hexdigest()


def archived_prefix(directory):
    rows = [json.loads(line) for line in (directory / 'decisions.jsonl').read_text().splitlines() if line.strip()]
    by_seq = {row['seq']: row for row in rows}
    if len(by_seq) != len(rows) or set(by_seq) != set(range(len(rows))):
        raise ValueError('Archived decisions must be a unique contiguous dispatch prefix')
    for seq, row in by_seq.items():
        if 'error' in row:
            raise ValueError('Error-bearing prefix needs explicit error replay support')
        png = (directory / f'obs-{seq:04d}.png').read_bytes()
        if hashlib.sha256(png).hexdigest() != row['image_sha256']:
            raise ValueError(f'Archived image hash mismatch seq={seq}')
    return by_seq


async def recover(name, rows, *, live=False, workers=8, output_round='r1-recovery', url='http://127.0.0.1:18891'):
    original = RUNS / 'r1' / name
    if (original / 'summary.json').exists():
        return {'episode': name, 'completed_reference': str(original / 'summary.json')}
    variant, seed_text = name.rsplit('-seed', 1)
    seed = int(seed_text)
    prefix = archived_prefix(original)
    checkpoint = json.loads((original / 'progress.json').read_text())
    output = RUNS / output_round / name
    output.mkdir(parents=True, exist_ok=True)
    if live and (output / 'summary.json').exists():
        return json.loads((output / 'summary.json').read_text())
    if live and (output / 'decisions.jsonl').exists():
        raise RuntimeError('Recovery already has decisions: choose a fresh --output-round to avoid overwriting')
    scheduler, source_sha = baseline_scheduler()
    rng = random.Random(seed)
    delays = [r['latency_s'] for r in rows]
    pending = []
    providers = []
    free_workers = asyncio.Queue()
    start = time.monotonic()
    seq = calls = errors = drops = consumed = new_calls = 0
    t, next_obs = 0., .45
    checked = False
    replay_render_hash_matches = 0
    missing_at_due = False

    async def new_decision(text, png):
        nonlocal new_calls
        # Called lazily only for missing decisions; replay-only never starts SSH.
        if not providers:
            for _ in range(workers):
                provider = await NativeProvider().start()
                providers.append(provider)
                free_workers.put_nowait(provider)
        provider = await free_workers.get()
        try:
            new_calls += 1
            return await provider.act(text, [png])
        finally:
            free_workers.put_nowait(provider)

    # Avoid concurrent lazy creation of duplicate pools on the first dispatches.
    pool_lock = asyncio.Lock()
    async def live_decision(text, png):
        async with pool_lock:
            if not providers:
                for _ in range(workers):
                    provider = await NativeProvider().start()
                    providers.append(provider)
                    free_workers.put_nowait(provider)
        return await new_decision(text, png)

    async with VisualRhythmEnv(url, virtual=True) as env:
        await env.start_virtual()
        try:
            while t < 30:
                await env.advance(t)
                scheduler.advance(t * 1000)
                changed = False
                while pending and pending[0][0] <= t + 1e-7:
                    due, rid, obs, future, recorded = heapq.heappop(pending)
                    if future is None and recorded is None:
                        missing_at_due = True
                        break
                    if recorded is not None:
                        if abs(recorded['arrival_s'] - t) > 1e-6:
                            raise AssertionError(f'Arrival mismatch seq={rid}: {t} != {recorded["arrival_s"]}')
                        answer, meta = recorded['answer'], recorded['metadata']
                        actions = parse(answer, obs, variant)
                        if actions != recorded['actions']:
                            raise AssertionError(f'Parsed actions differ seq={rid}')
                        consumed += 1
                    else:
                        try:
                            answer, meta = await future
                            actions = parse(answer, obs, variant)
                        except Exception as exc:
                            errors += 1
                            log = {'seq': rid, 'obs_s': obs.time_s, 'arrival_s': t,
                                   'error': type(exc).__name__ + ': ' + str(exc)[:250]}
                            with (output / 'decisions.jsonl').open('a') as handle:
                                handle.write(json.dumps(log) + '\n')
                            continue
                    scheduler.submit(str(rid), obs.time_s * 1000, actions, t * 1000,
                                     horizon_ms=1800, lanes=[0, 1, 2, 3])
                    changed = True
                    if live:
                        log = {'seq': rid, 'obs_s': obs.time_s, 'arrival_s': t,
                               'sampled_delay_s': due - obs.time_s, 'answer': answer,
                               'actions': actions, 'metadata': meta,
                               'image_sha256': hashlib.sha256(obs.png).hexdigest(),
                               'replayed': recorded is not None}
                        with (output / 'decisions.jsonl').open('a') as handle:
                            handle.write(json.dumps(log) + '\n')
                if changed:
                    await env.replace_schedule([{'time': a.game_ms / 1000, 'lane': a.lane} for a in scheduler.pending()])
                if abs(t - checkpoint['game_s']) <= 1e-6 and not checked:
                    value = await env.evaluator()
                    for key in ('score', 'counts'):
                        if value[key] != checkpoint[key]:
                            raise AssertionError(f'Checkpoint {key} mismatch: {value[key]} != {checkpoint[key]}')
                    checked = True
                    print('RECOVERY_CHECKPOINT ' + json.dumps({'episode': name, 'game_s': t, 'score': value['score'], 'counts': value['counts']}), flush=True)
                if missing_at_due:
                    break
                if t + 1e-7 >= next_obs:
                    if len(pending) < 8:
                        current = await env.screenshot()
                        recorded = prefix.get(seq)
                        if recorded is not None:
                            if abs(current.time_s - recorded['obs_s']) > 1e-6:
                                raise AssertionError(f'Observation timestamp mismatch seq={seq}')
                            png = (original / f'obs-{seq:04d}.png').read_bytes()
                            replay_render_hash_matches += hashlib.sha256(current.png).digest() == hashlib.sha256(png).digest()
                            obs = Observation(png, current.time_s, current.capture_start_s,
                                              current.capture_end_s, current.geometry, current.state)
                            future = None
                        else:
                            obs = current
                            future = asyncio.create_task(live_decision(prompt(obs, variant, delay_ms=[sorted(delays)[len(delays)//2]*1000, max(delays)*1000]), obs.png)) if live else None
                        delay = rng.choice(delays)
                        due = t + delay
                        if recorded is not None and abs(due - recorded['arrival_s']) > 1e-6:
                            raise AssertionError(f'RNG/delay mismatch seq={seq}')
                        if live:
                            (output / f'obs-{seq:04d}.png').write_bytes(obs.png)
                        heapq.heappush(pending, (due, seq, obs, future, recorded))
                        seq += 1
                        calls += 1
                    else:
                        drops += 1
                    next_obs += .30
                if not live and consumed == len(prefix) and checked:
                    break
                candidates = [30., next_obs]
                if pending:
                    candidates.append(pending[0][0])
                if scheduler.pending():
                    candidates.append(scheduler.pending()[0].game_ms / 1000)
                if not checked and checkpoint['game_s'] > t + 1e-7:
                    candidates.append(checkpoint['game_s'])
                t = min(x for x in candidates if x > t + 1e-7)
            validation = {'episode': name, 'prefix_length': len(prefix), 'prefix_replayed': consumed,
                          'checkpoint_verified': checked, 'new_model_calls': new_calls,
                          'archived_input_hashes_verified': len(prefix),
                          'current_render_exact_hash_matches': replay_render_hash_matches,
                          'scheduler_source_sha256': source_sha,
                          'original_decisions_sha256': hashlib.sha256((original / 'decisions.jsonl').read_bytes()).hexdigest(),
                          'limitations': ['Decorative particles use nondeterministic renderer timing; full replay screenshots may differ. Archived decision inputs are verified byte-for-byte.',
                                          'Core score/count checkpoint is checked, not hidden chart state. Missing decisions use freshly rendered screenshots.',
                                          'New subscription worker count affects research wall time only; virtual delay distribution and capacity remain the baseline.']}
            if not checked or consumed != len(prefix):
                raise AssertionError('Could not validate complete archived prefix before missing decision became due')
            (output / ('recovery-validation.json' if live else 'replay-validation.json')).write_text(json.dumps(validation, indent=2))
            if not live:
                print('RECOVERY_REPLAY_VALIDATED ' + json.dumps(validation), flush=True)
                return validation
            await env.advance(30)
            value = await env.evaluator()
            accuracy = value['score'] / max(1, value['total_notes'] * 1000)
            summary = {**value, **validation, 'accuracy': accuracy, 'variant': variant,
                       'seed': seed, 'calls': calls, 'drops': drops, 'errors': errors,
                       'wall_s': time.monotonic() - start, 'mode': 'subscription_latency_simulation_recovered',
                       'speed': 1, 'cadence_s': .30, 'real_workers': workers, 'virtual_capacity': 8,
                       'latency_scale': 1, 'passed': accuracy >= .95 and value['counts']['miss'] == 0,
                       'request_profile_sha256': hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
            (output / 'summary.json').write_text(json.dumps(summary, indent=2))
            (output / 'actions.json').write_text(json.dumps(await env.action_log()))
            print('RECOVERY_COMPLETE ' + json.dumps(summary), flush=True)
            return summary
        finally:
            futures = [item[3] for item in pending if item[3] is not None]
            for future in futures:
                future.cancel()
            await asyncio.gather(*futures, return_exceptions=True)
            await asyncio.gather(*(p.close() for p in providers), return_exceptions=True)


async def main(args):
    rows = [r for r in json.loads((RUNS / 'profile.json').read_text())['rows']
            if r['detail'] == 'high' and r.get('effort', 'low') == 'low']
    if not rows:
        raise RuntimeError('No baseline measured latency profile')
    names = args.only.split(',') if args.only else [p.name for p in sorted((RUNS / 'r1').iterdir())
                                                   if p.is_dir() and (p / 'decisions.jsonl').exists()]
    semaphore = asyncio.Semaphore(args.episodes)
    async def job(name):
        async with semaphore:
            return await recover(name, rows, live=args.live, workers=args.workers,
                                 output_round=args.output_round, url=args.url)
    results = await asyncio.gather(*(job(name) for name in names))
    output = RUNS / args.output_round
    output.mkdir(parents=True, exist_ok=True)
    # All completed baseline summaries are references; their episodes are never rerun.
    references = [str(p) for p in sorted((RUNS / 'r1').glob('*/summary.json'))]
    (output / ('manifest-live.json' if args.live else 'manifest-replay.json')).write_text(json.dumps({'results': results, 'completed_baseline_references': references}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', help='Comma-separated episode directory names')
    parser.add_argument('--episodes', type=int, default=3)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--output-round', default='r1-recovery')
    parser.add_argument('--url', default='http://127.0.0.1:18891')
    parser.add_argument('--live', action='store_true', help='Permit subscription calls for missing decisions')
    parser.add_argument('--replay-only', action='store_true', help='Default: no new model calls')
    arguments = parser.parse_args()
    if arguments.live and arguments.replay_only:
        parser.error('--live and --replay-only are mutually exclusive')
    asyncio.run(main(arguments))
