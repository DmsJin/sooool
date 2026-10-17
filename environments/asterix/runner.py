"""Single-request visual policy loop shared by profile development and realtime eval."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time

from direct_action_transport import DirectActionTransport
from simulate_5x import FPS, delay_frames, make_env, png, select_images


def parse_decision(answer, output_format):
    if output_format == 'action':
        if answer.strip() not in list('0123456789')[:9]:
            raise ValueError('Expected one action integer 0..8')
        return int(answer.strip()), None
    value = json.loads(answer)
    if not isinstance(value, dict) or type(value.get('action')) is not int or not 0 <= value['action'] <= 8:
        raise ValueError('Expected action integer 0..8')
    reason = value.get('reason')
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 400:
        raise ValueError('Expected a brief public English decision summary')
    return value['action'], reason.strip()


def build_task(root, recipe, mode):
    delays = json.loads((root / recipe['profile']).read_text())['capture_to_complete_seconds']
    for delay in delays:
        delay_frames(delay)
    values = sorted(delays)
    position = (len(values)-1)*.95
    lo, hi = math.floor(position), math.ceil(position)
    p95 = values[lo] + (values[hi]-values[lo])*(position-lo)
    prefix = (root / recipe['task_prefix']).read_text().format(
        mean_ms=statistics.mean(delays)*1000, median_ms=statistics.median(delays)*1000, p95_ms=p95*1000)
    if mode == 'realtime':
        prefix = prefix.replace('The virtual game advances', 'The real-time game advances continuously')
        prefix = prefix.replace('available only after a sampled complete API response delay.',
            'available when your actual subscription response completes; the game keeps advancing while you compute.')
        prefix = prefix.replace('Native subscription computation wall time does not advance this simulation.',
            'Actual subscription computation wall time DOES advance this real-time game.')
        prefix = prefix.replace('Measured previous API complete-response delay:',
            'Historical API context only; live subscription latency is measured in this run. Previous API delay:')
        if recipe.get('provider') == 'openai_api':
            prefix = prefix.replace('available when your actual subscription response completes;',
                'available when your complete legal action JSON arrives;')
            prefix = prefix.replace('subscription', 'API')
    task = prefix + (root / recipe['prompt']).read_text().strip() + '\n'
    if recipe['output_format'] == 'action_reason':
        replacements = {
            'Return only one integer:': 'Choose one action:',
            'Do not use tools, explain, or analyze aloud. Output the action integer immediately.':
                'Do not use tools. Follow the public output format below.',
            'Use this ordered decision procedure internally; output only the final action integer:':
                'Use this ordered decision procedure to select the action:',
            'Return one integer only.': 'Use the public output format below.',
        }
        for old, new in replacements.items():
            if old not in task:
                raise ValueError('Policy output contract changed: '+old)
            task = task.replace(old, new)
        task += '\n' + (root / recipe['output_instructions']).read_text()
    return task, delays


def run_episode(recipe, out, seed, horizon, task, delays, client, mode, env_factory=make_env):
    out.mkdir(parents=True, exist_ok=False)
    env, obs, info, noops = env_factory(seed)
    window = deque(maxlen=9)
    movement = DirectActionTransport()
    rng = random.Random(recipe['args']['latency_seed_offset']+seed)
    requests, pending, deliveries = [], None, []
    score, frames, drops, error = 0., 0, 0, None
    max_lag, status = 0., 'horizon'
    admitted_before = client.admitted_count() if hasattr(client, 'admitted_count') else 0
    started = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=1)

    def request(text, images, directory):
        answer, meta = client.act(text, images, directory)
        chosen, reason = parse_decision(answer, recipe['output_format'])
        return {'answer': answer, 'chosen': chosen, 'reason': reason, 'meta': meta}

    try:
        with (out/'steps.jsonl').open('w') as steps, (out/'issued.jsonl').open('w') as issued:
            for frame in range(horizon):
                if mode == 'realtime':
                    remaining = started + frame/FPS - time.monotonic()
                    if remaining > 0:
                        time.sleep(remaining)
                    max_lag = max(max_lag, time.monotonic()-started-frame/FPS)
                ready = []
                if pending is not None:
                    row, future = pending
                    available = frame >= row['action_ready_frame'] if mode == 'simulation' else future.done()
                    # Verify a terminal failure before claiming a new action was applied on this tick.
                    result = future.result() if available else None
                    early = client.poll_action() if mode == 'realtime' and hasattr(client, 'poll_action') else None
                    if early is not None:
                        if early['directory'] != f'call-{row["seq"]:05d}':
                            raise ValueError('Early action belongs to a different request')
                        ready = [{'seq': row['seq'], 'obs_frame': row['obs_frame'], 'chosen': early['chosen']}]
                        row['delivery_frame'] = frame
                        row['early_action'] = early
                        deliveries.append({'frame': frame, 'seq': row['seq'], 'mode': mode,
                            'capture_to_apply_s': (frame-row['obs_frame'])/FPS,
                            'actual_capture_to_apply_s':time.monotonic()-started-row['capture_wall_seconds'],
                            'terminal_pending': not future.done()})
                    if available:
                        if row['delivery_frame'] is None:
                            ready = [{'seq': row['seq'], 'obs_frame': row['obs_frame'], 'chosen': result['chosen']}]
                            deliveries.append({'frame': frame, 'seq': row['seq'], 'capture_to_apply_s':
                                frame/FPS-row['obs_frame']/FPS, 'mode': mode,
                                'actual_capture_to_apply_s':time.monotonic()-started-row['capture_wall_seconds']})
                            row['delivery_frame'] = frame
                        pending = None
                action = movement.advance(frame, ready)
                if frame % 4 == 0:
                    window.append((frame, png(obs)))
                    if pending is not None:
                        drops += 1
                    else:
                        images = select_images(window)
                        text = task + f'Current observation frame: {frame}. Image frames: {[f for f,_ in images]}. Current held action: {action}.\n'
                        text += 'Applied commands, oldest first, age_in_raw_frames:action: '+','.join(
                            str(frame-r['frame'])+':'+str(r['action']) for r in movement.applied[-8:])+'.\n'
                        sampled = rng.choice(delays) if mode == 'simulation' else None
                        row = {'seq': len(requests), 'obs_frame': frame, 'held_action': action,
                            'image_frames': [f for f,_ in images], 'image_sha256': [hashlib.sha256(im).hexdigest() for _,im in images],
                            'sampled_capture_to_complete_s': sampled,
                            'capture_wall_seconds':time.monotonic()-started,
                            'action_ready_frame': frame+delay_frames(sampled) if sampled is not None else None,
                            'score_at_issue': score, 'delivery_frame': None}
                        issued.write(json.dumps(row)+'\n');issued.flush()
                        future = pool.submit(request, text, [im for _,im in images], out/f'call-{row["seq"]:05d}')
                        requests.append((row, future));pending = (row, future)
                obs, reward, done, truncated, info = env.step(action)
                score += reward;frames = frame+1
                steps.write(json.dumps({'frame': frame, 'action': action, 'reward': reward, 'score': score, 'lives': info['lives']})+'\n')
                if frames % 60 == 0:
                    steps.flush()
                    (out/'progress.json').write_text(json.dumps({'frames':frames, 'game_seconds':frames/60,
                        'score':score, 'lives':info['lives'], 'calls':len(requests), 'mode':mode})+'\n')
                if done or truncated:
                    status = 'natural_end';break
            if mode == 'realtime':
                remaining=started+frames/FPS-time.monotonic()
                if remaining>0:time.sleep(remaining)
    except BaseException as exc:
        error = {'type':type(exc).__name__, 'message':str(exc)};status = 'interrupted'
    finally:
        elapsed = time.monotonic()-started
        env.close()
        pool.shutdown(wait=True)
        with (out/'decisions.jsonl').open('w') as log:
            for row, future in requests:
                try:
                    log.write(json.dumps({**row, **future.result()})+'\n')
                except BaseException as exc:
                    early = row.get('early_action')
                    applied = {'chosen':early['chosen'], 'reason':early['reason'],
                        'answer':json.dumps({'action':early['chosen'],'reason':early['reason']})} if early else {}
                    log.write(json.dumps({**row, **applied, 'error_type':type(exc).__name__})+'\n')
                    error = error or {'type':type(exc).__name__, 'message':str(exc)};status = 'interrupted'
        (out/'actions.json').write_text(json.dumps(movement.applied)+'\n')
        (out/'ignored_commands.json').write_text('[]\n')
        (out/'deliveries.json').write_text(json.dumps(deliveries)+'\n')
        paid = getattr(client, 'provider', None) == 'openai_api'
        summary = {'seed':seed, 'score':score, 'lives':info['lives'], 'frames':frames, 'game_seconds':frames/60,
            'reset_noops':noops, 'calls':len(requests), 'new_subscription_calls':0 if paid else len(requests), 'replayed_calls':0,
            'drops':drops, 'peak_inflight':int(bool(requests)), 'status':status, 'error':error,
            'mode':mode, 'provider':'openai_api' if paid else 'chatgpt_subscription',
            'paid_api_calls':client.admitted_count()-admitted_before if paid and hasattr(client,'admitted_count') else len(requests) if paid else 0,
            'environment_wall_seconds':elapsed, 'virtual_wall_seconds':frames/FPS,
            'max_frame_lag_seconds':max_lag if mode == 'realtime' else None,
            'limitation': 'Historical valid-response API latency; no provider-failure simulation.' if mode == 'simulation'
                else 'Actual API response latency at 12 raw FPS.' if paid
                else 'Actual subscription response latency; no paid ultrafast API claim.'}
        (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    if error:
        raise RuntimeError('Episode interrupted; partial evidence retained: '+str(error))
    return summary


def run_recipe(root, recipe, out, args, client_factory, mode='simulation'):
    if (recipe['args']['controller'],recipe['native_workers'],recipe['args']['virtual_capacity'],recipe['args']['episode_workers']) != ('direct',1,1,1):
        raise ValueError('Selected Asterix requires one request and unchanged direct model actions')
    recipe = dict(recipe)
    if getattr(args, 'provider', None) == 'api':recipe['provider'] = 'openai_api'
    task, delays = build_task(root, recipe, mode)
    (out/'task.txt').write_text(task)
    seeds = [args.seed] if args.seed is not None else recipe['args']['seeds']
    horizon = round(args.duration*60) if args.duration is not None else recipe['args']['max_frames']
    client = client_factory(output=out/'transport-worker', system=(root/recipe['system']).read_text())
    episodes = []
    try:
        for seed in seeds:
            try:
                episodes.append(run_episode(recipe, out/f'seed-{seed}', seed, horizon, task, delays, client, mode))
            except BaseException:
                partial=out/f'seed-{seed}'/'summary.json'
                if partial.exists():episodes.append(json.loads(partial.read_text()))
                raise
    finally:
        client.close()
        summary = {'episodes':episodes, 'mode':mode, 'paid_api_calls':sum(e.get('paid_api_calls',0) for e in episodes)}
        (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary
