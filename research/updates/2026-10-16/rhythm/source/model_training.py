"""Causal virtual episodes with native subscription model-authored tap plans.

The private event loop reveals each answer only at its sampled API delivery
time. Waiting for subscription computation at that event consumes wall time,
not additional virtual game time. This is never represented as real-time play.
No model tap time is converted, clamped, inferred, merged, or otherwise changed.
"""
import argparse
import asyncio
from collections import deque
from datetime import datetime, timezone
import hashlib
import heapq
import json
import math
from pathlib import Path
import random
import re
import time
import uuid

from .model_env import ModelVisualEnv
from .model_policy import prompt, parse
from .model_subscription import CheckedNativeProvider as NativeProvider

ROOT = Path(__file__).resolve().parents[2]


def _append(path, data):
    with path.open('a') as handle:
        handle.write(json.dumps(data, separators=(',', ':'), allow_nan=False) + '\n')


def load_delays(profile_path):
    profile = json.loads(Path(profile_path).read_text())
    rows = [row for row in profile['rows'] if row.get('status') == 'completed']
    delays = [row['metadata']['latency_s'] for row in rows]
    if not delays or any(type(delay) not in (int, float) or not math.isfinite(delay) or delay <= 0 for delay in delays):
        raise ValueError('Profile must contain completed rows with finite positive metadata.latency_s')
    # Keep every completed latency, including tails and schema-invalid answers.
    return profile, delays


async def run_episode(args, *, provider_factory=NativeProvider, env_factory=ModelVisualEnv):
    if getattr(args, 'joint_profile', None):
        from .model_joint_training import run_episode as run_joint_episode
        return await run_joint_episode(args, provider_factory=provider_factory, env_factory=env_factory)
    if getattr(args,'hide_rtt',False):
        raise ValueError('RTT ablation requires --joint-profile')
    if not getattr(args, 'profile', None):
        raise ValueError('Supply --profile or --joint-profile')
    if args.actors < 1 or not math.isfinite(args.cadence) or args.cadence <= 0 or args.max_requests < 1:
        raise ValueError('Invalid actor count, cadence or request ceiling')
    if args.frames not in (1, 2, 3) or not math.isfinite(args.duration) or args.duration <= 0:
        raise ValueError('Invalid frame count or episode duration')
    if not math.isfinite(args.clock_offset_ms):
        raise ValueError('External clock offset must be finite')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.candidate):
        raise ValueError('Candidate must be a path-safe identifier')
    from . import model_compact_policy,model_lean_policy
    policy=model_lean_policy if getattr(args,'lean',False) else model_compact_policy if getattr(args,'compact',False) else None
    make_prompt,parse_plan=(policy.prompt,policy.parse) if policy else (prompt,parse)
    profile, delays = load_delays(args.profile)
    rng = random.Random(args.seed)
    memory = Path(args.memory).read_text() if args.memory else ''
    output = Path(args.run_root) / (args.candidate + '-seed' + str(args.seed) + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    files = ['experiments/rhythm/model_training.py', 'experiments/rhythm/model_policy.py',
             'experiments/rhythm/model_env.py', 'experiments/rhythm/model_compact_policy.py','experiments/rhythm/model_lean_policy.py', 'experiments/rhythm/providers.py',
             'experiments/rhythm/model_subscription.py',
             'experiments/rhythm/scheduler.py', 'dist/model-executor.js',
             'dist/model-sim-clock.js', 'dist/game.js']
    frozen = {'subscription_outer': getattr(args,'outer','legacy'), 'protocol': 'direct_literal_model_tap_times_v1', 'candidate': args.candidate,
              'mode': 'native_subscription_virtual_api_delay_simulation', 'paid_api_calls': 0,
              'seed': args.seed, 'clock_offset_ms': args.clock_offset_ms, 'cadence_s': args.cadence,
              'actors': args.actors, 'frames': args.frames, 'max_requests': args.max_requests,
              'raw_ack_tail': 24,
              'duration_s': args.duration, 'profile_path': str(Path(args.profile).resolve()),
              'profile_sha256': hashlib.sha256(Path(args.profile).read_bytes()).hexdigest(),
              'profile_latency_samples_s': delays, 'memory_sha256': hashlib.sha256(memory.encode()).hexdigest() if memory else None,
              'trusted_chart_sha256': hashlib.sha256(Path(args.chart).read_bytes()).hexdigest() if args.chart else None,
              'source_sha256': {file: hashlib.sha256((ROOT / file).read_bytes()).hexdigest() for file in files},
              'started_at': datetime.now(timezone.utc).isoformat(),
              'limitations': ['Subscription computation time is separate from simulated API delivery delay.',
                             'No virtual outcome substitutes for a native real API acceptance run.']}
    (output / 'frozen.json').write_text(json.dumps(frozen, indent=2))
    providers = []
    available = asyncio.Queue()
    pending = []
    frames = deque(maxlen=args.frames)
    rtts = []
    request_count = dropped = errors = applied = rejected = 0
    game_s = 0.
    next_capture = 0.
    started = time.monotonic()

    async def infer(text, images):
        provider = await available.get()
        try:
            return await provider.act(text, images)
        finally:
            available.put_nowait(provider)

    try:
        for _ in range(args.actors):
            provider = await provider_factory().start()
            providers.append(provider)
            available.put_nowait(provider)
        async with env_factory(args.url, virtual=True, browser_executable=args.browser_executable,
                               chart_path=args.chart, clock_offset_ms=args.clock_offset_ms) as env:
            await env.start()
            capture_index = 0
            while game_s < args.duration:
                await env.advance(game_s)
                # Answer content is neither awaited nor inspected before its due event.
                while pending and pending[0][0] <= game_s + 1e-9:
                    due_s, sequence, sent_s, observation, future = heapq.heappop(pending)
                    row = {'request_version': sequence, 'sent_virtual_s': sent_s,
                           'delivery_virtual_s': game_s, 'sampled_due_virtual_s': due_s,
                           'sampled_rtt_ms': (due_s - sent_s) * 1000}
                    try:
                        answer, metadata = await future
                        plan = parse_plan(answer)
                        # This is the literal parsed model plan, including literal times.
                        receipt = await env.apply(plan)
                        row.update(answer=answer, metadata=metadata, plan=plan, receipt=receipt)
                        applied += 1
                        rejected += receipt.get('transaction_status') == 'rejected'
                    except Exception as error:
                        errors += 1
                        row['error'] = type(error).__name__ + ': ' + str(error)[:300]
                    rtts.append((due_s - sent_s) * 1000)
                    _append(output / 'decisions.jsonl', row)
                if game_s + 1e-9 >= next_capture:
                    frame = await env.capture()
                    image_name = f'frame-{capture_index:04d}.png'
                    (output / image_name).write_bytes(frame['png'])
                    frame_metadata = {key: frame[key] for key in ('capture_start_ms', 'capture_end_ms')}
                    frame_metadata.update(image=image_name, image_sha256=hashlib.sha256(frame['png']).hexdigest())
                    frames.append((frame, frame_metadata))
                    _append(output / 'captures.jsonl', {'virtual_s': game_s, **frame_metadata})
                    capture_index += 1
                    if len(pending) < args.actors and request_count < args.max_requests:
                        snapshot = await env.snapshot()
                        sequence = request_count + 1
                        observation = {'frames': [item[0] for item in frames],
                                       'external_now_ms': snapshot['clock_ms'],
                                       'pending_plans': snapshot.get('pending', []),
                                       'executed_acks': snapshot.get('rawacks', [])[-getattr(args,'ack_limit',24):],
                                       'rtt_history_ms': list(rtts[-8:]), 'model_memory': memory,
                                       'request_version': sequence, 'queue_version': snapshot['version']}
                        text = make_prompt(observation)
                        images = [item[0]['png'] for item in frames]
                        delay = rng.choice(delays)
                        future = asyncio.create_task(infer(text, images))
                        heapq.heappush(pending, (game_s + delay, sequence, game_s, observation, future))
                        _append(output / 'requests.jsonl', {'request_version': sequence, 'sent_virtual_s': game_s,
                                'delivery_virtual_s': game_s + delay, 'prompt': text,
                                'prompt_sha256': hashlib.sha256(text.encode()).hexdigest(),
                                'frames': [item[1] for item in frames]})
                        request_count += 1
                    else:
                        dropped += 1
                    next_capture += args.cadence
                    if capture_index % 10 == 0:
                        value = await env.trusted_evaluator()
                        progress = {'game_s': game_s, 'requests': request_count, 'pending': len(pending),
                                    'drops': dropped, 'errors': errors, 'evaluator': value,
                                    'wall_s': time.monotonic() - started}
                        (output / 'progress.json').write_text(json.dumps(progress))
                        print('MODEL_TRAIN_PROGRESS ' + json.dumps(progress), flush=True)
                candidates = [args.duration, next_capture]
                if pending:
                    candidates.append(pending[0][0])
                game_s = min(candidate for candidate in candidates if candidate > game_s + 1e-9)
            await env.advance(args.duration)
            evaluator = await env.trusted_evaluator()
            final_snapshot = await env.snapshot()
        unchanged = all(hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == sha for file, sha in frozen['source_sha256'].items())
        complete = evaluator['state'] == 'result' and evaluator['judged'] == evaluator['total_notes']
        summary = {'mode': frozen['mode'], 'candidate': args.candidate, 'seed': args.seed,
                   'evaluator': evaluator, 'complete': complete,
                   'passed': complete and evaluator['counts']['miss'] == 0 and evaluator.get('max_combo',0) == evaluator['total_notes'] and unchanged,
                   'legacy_two_miss_passed': complete and evaluator['counts']['miss'] <= 2 and unchanged,
                   'acceptance': 'Complete new 30s chart with at most 2 misses; all-PERFECT optional',
                   'all_perfect': complete and evaluator['counts']['perfect'] == evaluator['total_notes'],
                   'requests': request_count, 'delivered_plans': applied, 'transaction_rejections': rejected,
                   'errors': errors, 'dropped_capture_requests': dropped,
                   'undelivered_requests_at_end': len(pending), 'policy_unchanged': unchanged,
                   'final_raw_executor_snapshot': final_snapshot, 'paid_api_calls': 0,
                   'wall_s': time.monotonic() - started, 'output': str(output)}
        (output / 'summary.json').write_text(json.dumps(summary, indent=2))
        print('MODEL_TRAIN_COMPLETE ' + json.dumps(summary), flush=True)
        return summary
    finally:
        for _, _, _, _, future in pending:
            future.cancel()
        await asyncio.gather(*(item[4] for item in pending), return_exceptions=True)
        await asyncio.gather(*(provider.close() for provider in providers), return_exceptions=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outer',choices=('minimal','legacy'),default='minimal')
    parser.add_argument('--lean',action='store_true')
    parser.add_argument('--compact',action='store_true')
    parser.add_argument('--profile')
    parser.add_argument('--joint-profile', help='Trusted measured frame-age/API/transport tuples')
    parser.add_argument('--candidate', default='literal-model-v1')
    parser.add_argument('--seed', type=int, default=2)
    parser.add_argument('--clock-offset-ms', type=float, default=10000)
    parser.add_argument('--ack-limit',type=int,default=8)
    parser.add_argument('--actors', type=int, default=12)
    parser.add_argument('--cadence', type=float, default=.12)
    parser.add_argument('--frames', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--max-requests', type=int, default=400)
    parser.add_argument('--duration', type=float, default=30.001)
    parser.add_argument('--memory')
    parser.add_argument('--chart', help='Trusted-only chart path, never passed to policy workers')
    parser.add_argument('--url', default='http://127.0.0.1:18891')
    parser.add_argument('--browser-executable')
    parser.add_argument('--run-root', default=str(ROOT / 'experiments/rhythm/runs/model-timing'))
    args=parser.parse_args()
    if args.outer=='minimal':
        from .model_minimal_training import run
        asyncio.run(run(args))
    else:
        asyncio.run(run_episode(args))
