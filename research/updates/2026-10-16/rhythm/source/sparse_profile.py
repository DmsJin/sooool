"""Manual, strictly serial paid profiling for the sparse visual policy."""
import asyncio
from datetime import datetime, timezone
import fcntl
import getpass
import hashlib
import json
import math
import statistics
import uuid

from .policy import parse
from .providers import APIProvider
from .sparse_policy import prompt
from .visual_env import ROOT, VisualRhythmEnv

RUNS = ROOT / 'experiments/rhythm/runs'
TIMESTEPS = [1.4, 4.5, 7.6, 10.6, 13.7, 16.8, 20., 23.2]


async def calibrate(key, url='http://127.0.0.1:18891'):
    RUNS.mkdir(parents=True, exist_ok=True)
    lock = (RUNS / 'variant-profiling.serial.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('Another serial variant profiler is active')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    name = f'profile-pixels_sparse-{stamp}-{uuid.uuid4().hex[:6]}'
    images = RUNS / name
    images.mkdir(exist_ok=False)
    output = RUNS / (name + '.json')
    rows = []
    files = ['experiments/rhythm/sparse_policy.py', 'experiments/rhythm/sparse_profile.py',
             'experiments/rhythm/policy.py', 'experiments/rhythm/providers.py',
             'experiments/rhythm/scheduler.py', 'experiments/rhythm/visual_env.py',
             'dist/agent-bridge.js', 'dist/game.js']
    result = {'serial': True, 'concurrency': 1, 'variant': 'pixels_sparse',
              'requested_samples': 8, 'model': 'gpt-6.1-sol', 'tier': 'ultrafast',
              'detail': 'high', 'effort': 'low', 'max_output_tokens': 128,
              'images_per_request': 1, 'rows': rows,
              'input_protocol': 'canvas_pixels_exact_render_audio_timestamp_v1',
              'started_at': datetime.now(timezone.utc).isoformat(),
              'source_sha256': {file: hashlib.sha256((ROOT / file).read_bytes()).hexdigest() for file in files},
              'limitations': ['Eight serial samples do not characterize concurrent latency or a reliable P99.',
                             'Parse validity checks format and the sparse output constraint, not visual correctness.',
                             'The 128-token output cap includes reasoning; incomplete responses count as failures.']}

    def save():
        complete = [row for row in rows if row.get('status') == 'completed']
        latencies = sorted(row['latency_s'] for row in complete)
        result['groups'] = {'high_low': {'samples': len(complete), 'parse_valid': sum(row['parse_valid'] for row in complete)}}
        if latencies:
            result['groups']['high_low'].update(min_s=latencies[0], median_s=statistics.median(latencies),
                                              p95_s=latencies[math.ceil(.95 * len(latencies))-1], max_s=latencies[-1])
        output.write_text(json.dumps(result, indent=2))

    provider = APIProvider(key, RUNS, phase='profiling', detail='high', max_output=128, effort='low')
    try:
        async with VisualRhythmEnv(url, virtual=True) as env:
            await env.start_virtual()
            for index, target in enumerate(TIMESTEPS):
                await env.advance(target)
                obs = await env.screenshot()
                image = images / f'obs-{index:03d}.png'
                image.write_bytes(obs.png)
                text = prompt(obs)
                row = {'index': index, 'variant': 'pixels_sparse', 'target_game_s': target,
                       'obs_game_s': obs.time_s, 'geometry': obs.geometry, 'image_path': str(image),
                       'image_sha256': hashlib.sha256(obs.png).hexdigest(),
                       'prompt_sha256': hashlib.sha256(text.encode()).hexdigest(),
                       'sent_at': datetime.now(timezone.utc).isoformat()}
                try:
                    # Exactly one paid request in flight: deliberately no tasks or retries.
                    answer, meta = await provider.act(text, [obs.png])
                    row.update(meta, answer=answer, status='completed', received_at=datetime.now(timezone.utc).isoformat())
                    try:
                        raw = json.loads(answer)
                        if not isinstance(raw, list) or len(raw) > 2:
                            raise ValueError('Expected at most two targets')
                        previous_y = 0
                        for item in raw:
                            if not isinstance(item, list) or len(item) != 2 or type(item[1]) is not int or not previous_y <= item[1] <= 200:
                                raise ValueError('Sparse targets must be y=0..200 top-to-bottom')
                            previous_y = item[1]
                        row.update(parsed=parse(answer, obs, 'pixels_sparse'), parse_valid=True, valid=True)
                    except (ValueError, TypeError) as error:
                        row.update(parsed=[], parse_valid=False, valid=False, parse_error=type(error).__name__)
                except Exception as error:
                    row.update(status='error', parse_valid=False, valid=False,
                               error=type(error).__name__ + ': ' + str(error)[:250])
                    rows.append(row)
                    result['stopped_reason'] = row['error']
                    save()
                    break
                rows.append(row)
                save()
                print('SPARSE_PROFILE_SAMPLE ' + json.dumps({'index': index, 'latency_s': row['latency_s'],
                      'parse_valid': row['parse_valid'], 'cost_usd': row['cost_usd']}), flush=True)
    finally:
        await provider.close()
        result['finished_at'] = datetime.now(timezone.utc).isoformat()
        result['budget'] = provider.ledger.snapshot()
        save()
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    print('SPARSE_PROFILE_DONE ' + json.dumps({'path': str(output), 'groups': result['groups']}), flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18891')
    args = parser.parse_args()
    key = getpass.getpass('API key (process memory only): ')
    if not key:
        raise ValueError('Missing real API credential')
    asyncio.run(calibrate(key, args.url))
