"""Strictly serial API calibration for direct model-authored tap-time plans.

Full-board images and external capture timestamps only. No decisions are applied
while profiling. The existing cumulative paid ledger is mandatory.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import fcntl
import getpass
import hashlib
import json
from pathlib import Path
import statistics
import time
import uuid

from .model_policy import prompt, parse
from .providers import APIProvider

TIMESTEPS = [1.4, 4.5, 7.6, 10.6, 13.7, 16.8, 20., 23.2]


def observation_context(frames, snapshot, *, request_version, memory='', rtt_history_ms=()):
    return {'frames': frames, 'external_now_ms': snapshot['clock_ms'],
            'pending_plans': snapshot.get('pending', snapshot.get('pending_plans', [])),
            'executed_acks': snapshot.get('rawacks', snapshot.get('executed_acks', [])),
            'rtt_history_ms': list(rtt_history_ms), 'model_memory': memory,
            'request_version': request_version, 'queue_version': snapshot.get('version', snapshot.get('queue_version', 0))}


async def calibrate(args, key):
    from . import model_compact_policy,model_lean_policy
    policy=model_lean_policy if getattr(args,'lean',False) else model_compact_policy if getattr(args,'compact',False) else None
    make_prompt,parse_plan=(policy.prompt,policy.parse) if policy else (prompt,parse)
    # Imported only on execution: CLI help works before the environment is built.
    from .model_env import ModelVisualEnv
    run_root = Path(args.run_root).resolve()
    if not (run_root / 'budget.json').exists():
        raise ValueError('--run-root must contain the existing cumulative budget.json ledger')
    lock = (run_root / 'variant-profiling.serial.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('Another serial profiler is active')
    memory = Path(args.memory).read_text() if args.memory else ''
    tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:6]
    output = run_root / ('profile-model-timing-' + tag)
    output.mkdir(exist_ok=False)
    files = ['model_policy.py', 'model_compact_policy.py','model_lean_policy.py', 'model_profile.py', 'model_env.py', 'providers.py', 'scheduler.py',
             '../../dist/model-executor.js', '../../dist/model-sim-clock.js', '../../dist/game.js']
    source_root = Path(__file__).resolve().parent
    result = {'serial': True, 'concurrency': 1, 'variant': 'direct_model_timing',
              'model': 'gpt-6.1-sol', 'tier': 'ultrafast', 'effort': 'low', 'detail': args.detail,
              'max_output_tokens': args.max_output, 'images_per_request': args.frames,
              'memory_sha256': hashlib.sha256(memory.encode()).hexdigest() if memory else None,
              'source_sha256': {name: hashlib.sha256((source_root / name).read_bytes()).hexdigest() for name in files},
              'started_at': datetime.now(timezone.utc).isoformat(), 'rows': [],
              'limitations': ['Eight serial samples do not establish a reliable latency tail or concurrent throughput.',
                             'Schema validity is not a claim of visual or timing accuracy.',
                             'Only model-authored external tap times are returned; no controller timing correction is used.']}
    provider = APIProvider(key, run_root, phase='profiling', detail=args.detail, max_output=args.max_output, effort='low')
    rtts = []

    def save():
        values = sorted(row['metadata']['latency_s'] for row in result['rows'] if row.get('status') == 'completed')
        result['summary'] = {'completed': len(values), 'schema_valid': sum(row.get('schema_valid', False) for row in result['rows'])}
        if values:
            result['summary'].update(min_s=values[0], median_s=statistics.median(values), max_s=values[-1])
        (output / 'profile.json').write_text(json.dumps(result, indent=2))

    try:
        async with ModelVisualEnv(args.url, virtual=True, browser_executable=args.browser_executable) as env:
            await env.start()
            for index, target in enumerate(TIMESTEPS):
                frames = []
                for frame_index, game_s in enumerate((target - .2, target - .1, target) if args.frames == 3 else (target,)):
                    await env.advance(game_s)
                    frame = await env.capture()
                    frames.append(frame)
                    (output / f'obs-{index:02d}-{frame_index}.png').write_bytes(frame['png'])
                snapshot = await env.snapshot()
                context = observation_context(frames, snapshot, request_version=index + 1,
                                              memory=memory, rtt_history_ms=rtts)
                text = make_prompt(context)
                row = {'index': index, 'observation': {key: value for key, value in context.items() if key != 'frames'},
                       'frames': [{key: value for key, value in frame.items() if key != 'png'} for frame in frames],
                       'image_sha256': [hashlib.sha256(frame['png']).hexdigest() for frame in frames],
                       'prompt_sha256': hashlib.sha256(text.encode()).hexdigest(),
                       'sent_at': datetime.now(timezone.utc).isoformat()}
                try:
                    # Exactly one awaited call; no tasks, parallel requests or retries.
                    answer, metadata = await provider.act(text, [frame['png'] for frame in frames])
                    rtts.append(metadata['latency_s'] * 1000)
                    row.update(answer=answer, metadata=metadata, status='completed')
                    try:
                        row.update(plan=parse_plan(answer), schema_valid=True)
                    except (ValueError, TypeError) as error:
                        row.update(schema_valid=False, schema_error=type(error).__name__)
                except Exception as error:
                    row.update(status='error', schema_valid=False,
                               error=type(error).__name__ + ': ' + str(error)[:250])
                    result['rows'].append(row)
                    result['stopped_reason'] = row['error']
                    save()
                    break
                result['rows'].append(row)
                save()
                print('MODEL_PROFILE_SAMPLE ' + json.dumps({'index': index, 'latency_s': metadata['latency_s'],
                      'schema_valid': row['schema_valid'], 'cost_usd': metadata['cost_usd']}), flush=True)
    finally:
        await provider.close()
        result['budget'] = provider.ledger.snapshot()
        result['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    print('MODEL_PROFILE_DONE ' + json.dumps({'path': str(output / 'profile.json'), 'summary': result['summary']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18891')
    parser.add_argument('--browser-executable')
    parser.add_argument('--run-root', required=True, help='Existing cumulative paid ledger directory')
    parser.add_argument('--memory', help='Explicitly supplied model-authored memory text file')
    parser.add_argument('--lean',action='store_true')
    parser.add_argument('--compact', action='store_true')
    parser.add_argument('--frames', type=int, choices=(1,3), default=3)
    parser.add_argument('--detail', choices=('low','high'), default='high')
    parser.add_argument('--max-output', type=int, choices=(256,512,1024), default=512)
    args = parser.parse_args()
    key = getpass.getpass('API key (process memory only): ')
    if not key:
        raise ValueError('Missing API credential')
    asyncio.run(calibrate(args, key))
