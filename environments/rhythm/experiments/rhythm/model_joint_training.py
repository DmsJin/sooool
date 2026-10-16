"""Subscription research with causal, correlated screenshot age and API delivery.

No paid calls are made here. Joint conditions remain in the trusted event loop;
actors receive only past pixels and their original external capture timestamps.
"""
import asyncio
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
from .model_subscription import CheckedNativeProvider as NativeProvider
from .model_training import ROOT, _append


def load_joint_delays(path):
    profile = json.loads(Path(path).read_text())
    conditions = []
    for row in profile['rows']:
        if row.get('status') != 'completed':
            continue
        values = tuple(row.get(key) for key in ('api_rtt_s', 'frame_age_s', 'transport_overhead_s'))
        if any(type(x) not in (float, int) or not math.isfinite(x) for x in values):
            raise ValueError('Completed joint rows must contain finite numerical delays')
        if values[0] <= 0 or values[1] < 0 or values[2] < 0:
            raise ValueError('API delay must be positive; frame age and overhead nonnegative')
        conditions.append(values)
    if not conditions:
        raise ValueError('Joint profile has no completed rows')
    return profile, conditions


async def run_episode(args, *, provider_factory=NativeProvider, env_factory=ModelVisualEnv):
    if (type(args.actors) is not int or args.actors < 1 or args.frames != 1
            or not math.isfinite(args.cadence) or args.cadence <= 0
            or not math.isfinite(args.duration) or args.duration <= 0
            or type(args.max_requests) is not int or args.max_requests < 1
            or not math.isfinite(args.clock_offset_ms)
            or not re.fullmatch(r'[A-Za-z0-9_-]+', args.candidate)):
        raise ValueError('Invalid joint episode configuration; only frames=1 is supported')
    from . import model_policy, model_compact_policy, model_lean_policy
    policy = model_lean_policy if getattr(args, 'lean', False) else model_compact_policy if getattr(args, 'compact', False) else model_policy
    hide_rtt=getattr(args,'hide_rtt',False)
    if hide_rtt and not getattr(args,'lean',False):
        raise ValueError('RTT ablation requires the lean observation codec')
    _, conditions = load_joint_delays(args.joint_profile)
    memory = Path(args.memory).read_text() if args.memory else ''
    rng = random.Random(args.seed)
    output = Path(args.run_root) / (args.candidate + '-seed' + str(args.seed) + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    files = ['experiments/rhythm/' + name for name in (
        'model_joint_training.py', 'model_training.py', 'model_policy.py', 'model_compact_policy.py',
        'model_lean_policy.py', 'model_env.py', 'model_subscription.py', 'providers.py', 'scheduler.py',
        'model_outer_provider.py', 'subscription_outer_worker.py')]
    files += ['dist/model-executor.js', 'dist/model-sim-clock.js', 'dist/game.js',
              'experiments/rhythm/outer/minimal-system.txt']
    frozen = dict(mode='subscription_virtual_joint_delay_simulation', paid_api_calls=0,
                  candidate=args.candidate, seed=args.seed, clock_offset_ms=args.clock_offset_ms,
                  cadence_s=args.cadence, actors=args.actors, frames=1, max_requests=args.max_requests,
                  duration_s=args.duration, lean=getattr(args, 'lean', False), compact=getattr(args, 'compact', False),
                  outer=getattr(args, 'outer', 'legacy'), raw_ack_tail=getattr(args, 'ack_limit', 8),
                  hide_rtt=hide_rtt,
                  joint_profile_path=str(Path(args.joint_profile).resolve()),
                  joint_profile_sha256=hashlib.sha256(Path(args.joint_profile).read_bytes()).hexdigest(),
                  joint_conditions_s=conditions, memory_sha256=hashlib.sha256(memory.encode()).hexdigest(),
                  trusted_chart_sha256=hashlib.sha256(Path(args.chart).read_bytes()).hexdigest() if args.chart else None,
                  source_sha256={f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files},
                  started_at=datetime.now(timezone.utc).isoformat(),
                  limitations=['Subscription wall computation is separate from imposed virtual delivery.',
                               'Virtual evidence is not native API acceptance.',
                               'Initial frame age is truncated at episode start, without timestamp alteration.'])
    (output / 'frozen.json').write_text(json.dumps(frozen, indent=2))
    events = []
    calendar = {}
    index = 0
    while index * args.cadence < args.duration - 1e-9:
        issue = index * args.cadence
        api, age, overhead = rng.choice(conditions)
        capture = max(0., issue - age)
        calendar[index] = dict(issue_s=issue, capture_s=capture, api_rtt_s=api,
                               frame_age_s=age, transport_overhead_s=overhead,
                               due_s=issue + api + overhead)
        heapq.heappush(events, (capture, 1, index))
        heapq.heappush(events, (issue, 2, index))
        index += 1
    providers, tasks, retained = [], {}, {}
    available = asyncio.Queue()
    rtts = []
    sent = dropped = errors = applied = rejected = 0
    started = time.monotonic()

    async def infer(text, png):
        provider = await available.get()
        try:
            return await provider.act(text, [png])
        finally:
            available.put_nowait(provider)

    try:
        for _ in range(args.actors):
            provider = await provider_factory().start()
            providers.append(provider)
            available.put_nowait(provider)
        frozen['provider_configurations'] = [getattr(p, 'configuration', None) for p in providers]
        (output / 'frozen.json').write_text(json.dumps(frozen, indent=2))
        async with env_factory(args.url, virtual=True, browser_executable=args.browser_executable,
                               chart_path=args.chart, clock_offset_ms=args.clock_offset_ms) as env:
            await env.start()
            while events and events[0][0] <= args.duration:
                game_s, kind, event_index = heapq.heappop(events)
                await env.advance(game_s)
                condition = calendar[event_index]
                if kind == 0:
                    sequence, future = tasks.pop(event_index)
                    row = dict(request_version=sequence, sent_virtual_s=condition['issue_s'],
                               delivery_virtual_s=game_s, sampled_due_virtual_s=condition['due_s'],
                               joint_condition=condition)
                    try:
                        # Even an already-completed task is not observed before this event.
                        answer, metadata = await future
                        plan = policy.parse(answer)
                        receipt = await env.apply(plan)
                        row.update(answer=answer, metadata=metadata, plan=plan, receipt=receipt)
                        applied += 1
                        rejected += receipt.get('transaction_status') == 'rejected'
                    except Exception as error:
                        errors += 1
                        row['error'] = type(error).__name__ + ': ' + str(error)[:300]
                    rtts.append(condition['api_rtt_s'] * 1000)
                    _append(output / 'decisions.jsonl', row)
                elif kind == 1:
                    frame = await env.capture()
                    name = f'frame-{event_index:04d}.png'
                    (output / name).write_bytes(frame['png'])
                    metadata = {k: v for k, v in frame.items() if k != 'png'}
                    metadata.update(image=name, image_sha256=hashlib.sha256(frame['png']).hexdigest())
                    retained[event_index] = (frame, metadata)
                    _append(output / 'captures.jsonl', dict(calendar_index=event_index, virtual_s=game_s, **metadata))
                else:
                    frame, metadata = retained.pop(event_index)
                    if len(tasks) >= args.actors or sent >= args.max_requests:
                        dropped += 1
                        _append(output / 'drops.jsonl', dict(calendar_index=event_index, issue_virtual_s=game_s,
                                reason='inflight_capacity' if len(tasks) >= args.actors else 'request_ceiling'))
                        continue
                    snapshot = await env.snapshot()
                    sequence = sent + 1
                    observation = dict(frames=[frame], external_now_ms=snapshot['clock_ms'],
                                       pending_plans=snapshot.get('pending', []),
                                       executed_acks=snapshot.get('rawacks', [])[-getattr(args, 'ack_limit', 8):],
                                       rtt_history_ms=rtts[-8:], model_memory=memory,
                                       request_version=sequence, queue_version=snapshot['version'])
                    text = policy.prompt(observation,include_rtt=False) if hide_rtt else policy.prompt(observation)
                    tasks[event_index] = (sequence, asyncio.create_task(infer(text, frame['png'])))
                    heapq.heappush(events, (condition['due_s'], 0, event_index))
                    _append(output / 'requests.jsonl', dict(request_version=sequence, sent_virtual_s=game_s,
                            delivery_virtual_s=condition['due_s'], joint_condition=condition, frames=[metadata],
                            prompt=text, prompt_sha256=hashlib.sha256(text.encode()).hexdigest()))
                    sent += 1
                if kind == 2 and event_index % 10 == 0:
                    progress = dict(game_s=game_s, requests=sent, pending=len(tasks), drops=dropped,
                                    errors=errors, evaluator=await env.trusted_evaluator(), wall_s=time.monotonic()-started)
                    (output / 'progress.json').write_text(json.dumps(progress))
                    print('MODEL_JOINT_PROGRESS ' + json.dumps(progress), flush=True)
            await env.advance(args.duration)
            evaluator = await env.trusted_evaluator()
            snapshot = await env.snapshot()
            (output / 'final_snapshot.json').write_text(json.dumps(snapshot, indent=2))
        unchanged = all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == sha for f, sha in frozen['source_sha256'].items())
        complete = evaluator['state'] == 'result' and evaluator['judged'] == evaluator['total_notes'] == 52
        summary = dict(mode=frozen['mode'], candidate=args.candidate, seed=args.seed, evaluator=evaluator,
                       complete=complete, passed=complete and evaluator['counts']['miss'] == 0 and evaluator.get('max_combo',0) == 52 and unchanged,
                       legacy_two_miss_passed=complete and evaluator['counts']['miss'] <= 2 and unchanged,
                       requests=sent, delivered_plans=applied, transaction_rejections=rejected, errors=errors,
                       dropped_capture_requests=dropped, undelivered_requests_at_end=len(tasks),
                       policy_unchanged=unchanged, paid_api_calls=0, wall_s=time.monotonic()-started, output=str(output))
        (output / 'summary.json').write_text(json.dumps(summary, indent=2))
        print('MODEL_JOINT_COMPLETE ' + json.dumps(summary), flush=True)
        return summary
    finally:
        for _, task in tasks.values():
            task.cancel()
        await asyncio.gather(*(task for _, task in tasks.values()), return_exceptions=True)
        await asyncio.gather(*(p.close() for p in providers), return_exceptions=True)
