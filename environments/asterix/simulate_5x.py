"""12 raw FPS, empirical API delay, eight virtual workers; native subscription only.

Native model computations pause the environment; their wall time is recorded but is
never substituted for the sampled API latency. No key or direct API path exists.
"""
import argparse
import concurrent.futures as cf
from collections import deque
import hashlib
import heapq
import io
import json
import math
from pathlib import Path
import random
import statistics
import sys
import threading
import time

from hop_controller_v2 import HopControllerV2
from hop_controller_v3 import HopControllerV3
from hop_controller_v4 import HopControllerV4

FPS = 12
CAPACITY = 8


def png(obs):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(obs).resize((224, 224), Image.Resampling.BILINEAR).save(buf, format='PNG')
    return buf.getvalue()


def delay_frames(seconds, scale=1.):
    if not math.isfinite(seconds) or seconds <= 0 or not math.isfinite(scale) or scale < 1:
        raise ValueError('Positive latency and finite scale >= 1 required')
    return max(1, math.ceil(seconds * scale * FPS))


def select_images(window):
    n = len(window)
    return [window[i] for i in sorted({0, max(0, n-3), n-1})]


def make_env(seed):
    import gymnasium as gym
    import ale_py
    gym.register_envs(ale_py)
    env = gym.make('ALE/Asterix-v5', render_mode='rgb_array', obs_type='rgb', frameskip=1,
                   repeat_action_probability=0., full_action_space=False, mode=0, difficulty=0,
                   max_num_frames_per_episode=108000)
    obs, info = env.reset(seed=seed)
    noops = int(env.unwrapped.np_random.integers(1, 31))
    for _ in range(noops):
        obs, _, done, truncated, info = env.step(0)
        if done or truncated:
            obs, info = env.reset()
    assert env.unwrapped.get_action_meanings() == ['NOOP','UP','RIGHT','LEFT','DOWN','UPRIGHT','UPLEFT','DOWNRIGHT','DOWNLEFT']
    return env, obs, info, noops


def percentile(values, fraction):
    x = sorted(values)
    position = (len(x)-1)*fraction
    lo, hi = math.floor(position), math.ceil(position)
    return x[lo] + (x[hi]-x[lo])*(position-lo)


def base_prompt(strategy, delays, scale, controller='v3'):
    label = 'Measured previous API' if scale == 1 else 'Hypothetical slower API'
    text = (
        'Play Atari Asterix. Collect useful objects and avoid lyres. Return only one integer: '
        '0=NOOP, 1=UP, 2=RIGHT, 3=LEFT, 4=DOWN, 5=UPRIGHT, 6=UPLEFT, 7=DOWNRIGHT, 8=DOWNLEFT.\n'
        'The virtual game advances at 12 raw frames per second, 5 times slower than normal 60 FPS. '
        'Images are chronological; use their frame timestamps. The supplied history spans up to 32 raw '
        'frames, with the middle image 8 raw frames old and the newest image current. At most eight '
        'requests are in flight; observations are dropped when all workers are busy. A command becomes '
        'available only after a sampled complete API response delay. The newest completed observation '
        'wins and stale commands are discarded. UP/DOWN lasts at most four raw frames, then releases; '
        'LEFT/RIGHT continues. Further vertical commands based on observations before that hop finished '
        'cannot start or reverse another hop; an active hop finishes at its original deadline. '
        'An explicit nonvertical command can release it early. Wait for a fresh observation before '
        'requesting another row change. Native subscription computation wall time does not advance '
        'this simulation. Do not use tools, explain, or analyze aloud. Output the action integer immediately.\n'
        f'{label} complete-response delay: mean {statistics.mean(delays)*scale*1000:.0f} ms, '
        f'median {statistics.median(delays)*scale*1000:.0f} ms, '
        f'P95 {percentile(delays,.95)*scale*1000:.0f} ms. '
        'The actual delay of your request is unknown.\n' + strategy.strip() + '\n'
    )
    if controller in ('v3','v4'):
        start = text.index('UP/DOWN lasts at most four raw frames')
        end = text.index('Native subscription computation wall time', start)
        text = text[:start] + (
            'Any action containing UP/DOWN executes as one atomic four-raw-frame row hop, '
            'then ALL movement components release to NOOP, including the horizontal component '
            'of a diagonal hop. A reply captured before that hop finished cannot cancel, reverse, '
            'or alter the hop, and cannot change movement after landing either: the ENTIRE stale '
            'command is ignored. Wait for an observation captured at or after hop completion '
            'before commanding movement in the new row. Pure LEFT/RIGHT commands from fresh '
            'observations continue until replaced. '
        ) + text[end:]
        if controller == 'v4':
            text = text.replace('then ALL movement components release to NOOP, including the horizontal component of a diagonal hop.',
                'then its vertical component releases; a diagonal hop retains its LEFT/RIGHT component until a fresh command replaces it.')
    return text


class VirtualQueue:
    def __init__(self, capacity=CAPACITY):
        self.free = [0]*capacity
        self.ready = []
        self.peak = 0

    def available(self, frame):
        return next((i for i, due in enumerate(self.free) if due <= frame), None)

    def submit(self, frame, seq, future, delay):
        slot = self.available(frame)
        if slot is None:
            raise RuntimeError('Virtual worker capacity exceeded')
        due = frame + delay
        self.free[slot] = due
        heapq.heappush(self.ready, (due, seq, frame, future))
        self.peak = max(self.peak, sum(t > frame for t in self.free))
        return slot, due

    def advance(self, frame, controller):
        ready = []
        while self.ready and self.ready[0][0] <= frame:
            ready.append(heapq.heappop(self.ready))
        rows = []
        if ready:
            _, seq, obs_frame, future = max(ready, key=lambda r: r[1])
            if seq > controller.last:
                result = future.result()
                rows = [{'seq':seq, 'obs_frame':obs_frame, 'chosen':result['chosen']}]
        return controller.advance(frame, rows)


class NativePool:
    def __init__(self, args):
        self.args = args
        self.stop_percent = getattr(args, "quota_stop_percent", 50)
        if type(self.stop_percent) is not int or not 1 <= self.stop_percent <= 80:
            raise ValueError("Quota stop must be from 1 to 80")
        self.local = threading.local()
        self.lock = threading.Lock()
        self.clients = []
        self.stopped = threading.Event()
        self.pool = cf.ThreadPoolExecutor(max_workers=CAPACITY)

    def request(self, prompt, images, directory):
        from case_subscription_client import CaseSubscriptionClient
        from subscription_quota import read_limits, require_headroom
        if self.stopped.is_set():
            raise RuntimeError('Stopped before issuing another subscription request')
        try:
            if not hasattr(self.local, 'client'):
                with self.lock:
                    client = CaseSubscriptionClient(self.args.suite,
                        self.args.output/f'worker-{len(self.clients)}', profile='minimal',
                        quota_stop_percent=self.stop_percent, system_file=self.args.minimal_system_file)
                    self.clients.append(client)
                    self.local.client = client
            directory.mkdir(parents=True)
            client = self.local.client
            quota = read_limits(client.runner, directory/'quota-request.json')
            require_headroom(quota, self.stop_percent)
            if self.stopped.is_set():
                raise RuntimeError('Stopped before model dispatch')
            answer, meta = client.act(prompt, images, directory/'call')
            if answer.strip() not in [str(i) for i in range(9)]:
                raise ValueError('One integer action required')
            result = {'chosen':int(answer.strip()), 'answer':answer, 'meta':meta, 'quota_before':quota}
            (directory/'result.json').write_text(json.dumps(result)+'\n')
            return result
        except BaseException:
            self.stopped.set()
            raise

    def submit(self, *args):
        return self.pool.submit(self.request, *args)

    def close(self):
        self.pool.shutdown(wait=True)
        for client in self.clients:
            client.close()


def verify_replay(root):
    """Verify old paid actions, rewards, lives and all issued image hashes, no model."""
    summary = json.loads((root/'summary.json').read_text())
    steps = [json.loads(l) for l in (root/'steps.jsonl').read_text().splitlines()]
    requests = [json.loads(l) for l in (root/'requests.jsonl').read_text().splitlines()]
    by_frame = {r['obs_frame']:r for r in requests}
    assert len(by_frame) == len(requests)
    env, obs, info, noops = make_env(summary['seed'])
    assert noops == summary['reset_noops']
    window = deque(maxlen=9)
    score = 0.
    checked = 0
    try:
        for frame, step in enumerate(steps):
            assert step['frame'] == frame
            if frame % 4 == 0:
                window.append((frame, png(obs)))
            if frame in by_frame:
                images = select_images(window)
                hashes = [hashlib.sha256(im).hexdigest() for _, im in images]
                assert hashes == by_frame[frame]['image_sha256'], f'image mismatch at frame {frame}'
                checked += 1
            obs, reward, done, truncated, info = env.step(step['action'])
            score += reward
            assert reward == step['reward'] and score == step['score'] and info.get('lives') == step['lives'], frame
        assert score == summary['score'] and len(steps) == summary['frames']
        assert checked == len(requests)
        return {'seed':summary['seed'], 'verified_frames':len(steps), 'verified_requests':checked,
                'score':score, 'lives':info.get('lives'), 'reset_noops':noops, 'model_calls':0}
    finally:
        env.close()


def run_episode(args, seed, pool, prompt_base, delays):
    directory = args.output/f'seed-{seed}'
    directory.mkdir()
    env, obs, info, noops = make_env(seed)
    controller = {'v2':HopControllerV2,'v3':HopControllerV3,'v4':HopControllerV4}[getattr(args,'controller','v3')]()
    queue = VirtualQueue()
    rng = random.Random(args.latency_seed_offset+seed)
    window = deque(maxlen=9)
    score, frames, calls, drops = 0., 0, 0, 0
    requests = []
    replayed = 0
    replay = []
    replay_steps = []
    if args.replay_root:
        prior = args.replay_root/f'seed-{seed}'
        prior_summary = json.loads((prior/'summary.json').read_text())
        prefix_only = bool(prior_summary.get('error'))
        replay_file = 'completed_prefix.jsonl' if prefix_only else 'decisions.jsonl'
        step_file = 'resume_steps.jsonl' if prefix_only else 'steps.jsonl'
        replay = [json.loads(l) for l in (prior/replay_file).read_text().splitlines()]
        replay_steps = [json.loads(l) for l in (prior/step_file).read_text().splitlines()]
        if any('chosen' not in r for r in replay):
            raise ValueError('Only a completed error-free prefix can be resumed')
    started = time.perf_counter()
    status = 'horizon'
    error = None
    try:
        with (directory/'steps.jsonl').open('w') as steps, (directory/'issued.jsonl').open('w') as issued:
            for frame in range(args.max_frames):
                action = queue.advance(frame, controller)
                if frame % 4 == 0:
                    window.append((frame, png(obs)))
                    if queue.available(frame) is None:
                        drops += 1
                    else:
                        images = select_images(window)
                        text = prompt_base+f'Current observation frame: {frame}. Image frames: {[f for f,_ in images]}. Current held action: {action}.\n'
                        text += 'Applied commands, oldest first, age_in_raw_frames:action: '+','.join(str(frame-r['frame'])+':'+str(r['action']) for r in controller.applied[-8:])+'.\n'
                        sampled_s = rng.choice(delays)*args.latency_scale
                        hashes = [hashlib.sha256(im).hexdigest() for _,im in images]
                        if calls < len(replay):
                            previous = replay[calls]
                            checks = {'seq':calls,'obs_frame':frame,'held_action':action,'image_sha256':hashes,
                                      'sampled_capture_to_complete_s':sampled_s}
                            if any(previous[k] != v for k,v in checks.items()):
                                raise ValueError(f'Replay mismatch before new inference at call {calls}')
                            future = cf.Future()
                            future.set_result({**previous,'replayed_without_model_call':True})
                            replayed += 1
                        else:
                            if frame < len(replay_steps):
                                raise ValueError('Replay prefix missing an issued command')
                            future = pool.submit(text,[im for _,im in images],directory/f'call-{calls:05d}')
                        slot, due = queue.submit(frame, calls, future, delay_frames(sampled_s))
                        row = {'seq':calls,'obs_frame':frame,'held_action':action,'image_frames':[f for f,_ in images],
                               'image_sha256':hashes,
                               'sampled_capture_to_complete_s':sampled_s,'action_ready_frame':due,
                               'virtual_worker_slot':slot,'score_at_issue':score}
                        requests.append((row,future))
                        issued.write(json.dumps(row)+'\n'); issued.flush()
                        calls += 1
                obs,reward,done,truncated,info = env.step(action)
                score += reward
                frames = frame+1
                step = {'frame':frame,'action':action,'reward':reward,'score':score,'lives':info.get('lives')}
                if frame < len(replay_steps) and step != replay_steps[frame]:
                    raise ValueError(f'Replay step mismatch at frame {frame}')
                steps.write(json.dumps(step)+'\n')
                if frames % 60 == 0:
                    steps.flush()
                    progress = {'seed':seed,'frames':frames,'game_seconds':frames/60,
                                'score':score,'lives':info.get('lives'),'calls':calls,'drops':drops,'status':'running'}
                    temporary = directory/'progress.tmp'
                    temporary.write_text(json.dumps(progress)+'\n')
                    temporary.replace(directory/'progress.json')
                if frames % 300 == 0:
                    steps.flush()
                    print(json.dumps({'event':'progress','seed':seed,'game_seconds':frames/60,'virtual_wall_seconds':frames/FPS,
                                      'score':score,'lives':info.get('lives'),'calls':calls,'drops':drops}),flush=True)
                if done or truncated:
                    status = 'natural_end'
                    break
    except BaseException as exc:
        status = 'stopped_or_error'
        error = {'type':type(exc).__name__,'message':str(exc)}
        pool.stopped.set()
    finally:
        env.close()
        (directory/'actions.json').write_text(json.dumps(controller.applied)+'\n')
        if hasattr(controller,'ignored'):
            (directory/'ignored_commands.json').write_text(json.dumps(controller.ignored)+'\n')
        completed_prefix = []
        contiguous = True
        with (directory/'decisions.jsonl').open('w') as decisions:
            for row, future in requests:
                try:
                    result = future.result()
                    record = {**row,**result}
                    decisions.write(json.dumps(record)+'\n')
                    if contiguous:
                        completed_prefix.append(record)
                except BaseException as exc:
                    contiguous = False
                    if error is None:
                        error = {'type':type(exc).__name__,'message':str(exc)}
                        status = 'stopped_or_error'
                    decisions.write(json.dumps({**row,'error_type':type(exc).__name__})+'\n')
        (directory/'completed_prefix.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in completed_prefix))
        resume_frame = frames
        if error:
            if len(completed_prefix) < len(requests):
                resume_frame = min(frames,requests[len(completed_prefix)][0]['obs_frame'])
            prefix_steps = (directory/'steps.jsonl').read_text().splitlines()[:resume_frame]
            (directory/'resume_steps.jsonl').write_text(''.join(line+'\n' for line in prefix_steps))
        result = {'seed':seed,'score':score,'frames':frames,'game_seconds':frames/60,
                  'virtual_wall_seconds':frames/FPS,'lives':info.get('lives'),'reset_noops':noops,
                  'calls':calls,'replayed_calls':replayed,'new_subscription_calls':calls-replayed,
                  'completed_prefix_calls':len(completed_prefix),'resume_frame_raw':resume_frame,
                  'drops':drops,'peak_virtual_inflight':queue.peak,'status':status,
                  'error':error,'native_wall_seconds':time.perf_counter()-started,'paid_api_calls':0}
        (directory/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'event':'episode',**result}),flush=True)
    return result


def run(args):
    sys.path.insert(0, str(args.source))
    profile = json.loads(args.profile.read_text())
    delays = profile['capture_to_complete_seconds']
    for d in delays:
        delay_frames(d, args.latency_scale)
    strategy = args.strategy.read_text()
    args.output.mkdir(parents=True, exist_ok=False)
    prompt_base = base_prompt(strategy, delays, args.latency_scale, getattr(args,'controller','v3'))
    (args.output/'prompt.txt').write_text(prompt_base)
    config = {k:str(v) if isinstance(v, Path) else v for k,v in vars(args).items()}
    config.update(virtual_raw_fps=FPS, normal_game_fps=60, slowdown=5,
                  capacity=CAPACITY, observation_stride=4, history_span=32,
                  wrapper_profile='minimal', reasoning_effort='low', model='gpt-6.1-sol',
                  quota_stop_percent=getattr(args,"quota_stop_percent",50), paid_api_calls=0,
                  controller={'v2':'HopControllerV2: stale vertical does not interrupt active hop',
                              'v3':'HopControllerV3: atomic hop, neutral landing, all commands require post-hop observation',
                              'v4':'HopControllerV4: atomic hop, horizontal continuation, all commands require post-hop observation'}[getattr(args,'controller','v3')],
                  latency_method='Empirical IID capture-to-complete; same delay frees virtual worker',
                  profile_sha256=hashlib.sha256(args.profile.read_bytes()).hexdigest(),
                  strategy_sha256=hashlib.sha256(args.strategy.read_bytes()).hexdigest(),
                  caveat='Previous API policy latency; new prompt API latency unmeasured. Native wall times are separate.')
    if args.replay_root:
        prior_config = json.loads((args.replay_root/'config.json').read_text())
        for key in ['profile_sha256','strategy_sha256','latency_scale','latency_seed_offset',
                    'virtual_raw_fps','controller','wrapper_profile']:
            if prior_config[key] != config[key]:
                raise ValueError(f'Replay configuration mismatch: {key}')
        if args.max_frames < prior_config['max_frames']:
            raise ValueError('Replay extension must not shorten the horizon')
    sources = args.output/'source'
    sources.mkdir()
    config['source_sha256'] = {}
    for path in [Path(__file__),Path(__file__).with_name('hop_controller_v2.py'),
                 Path(__file__).with_name('case_subscription_client.py'),
                 Path(__file__).with_name('hop_controller_v3.py'),
                 Path(__file__).with_name('hop_controller_v4.py'),
                 args.source/'subscription_client.py',args.source/'subscription_quota.py']:
        data = path.read_bytes()
        (sources/path.name).write_bytes(data)
        config['source_sha256'][path.name] = hashlib.sha256(data).hexdigest()
    config['minimal_system_sha256'] = hashlib.sha256(args.minimal_system_file.read_bytes()).hexdigest()
    (args.output/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    pool = NativePool(args)
    episodes = []
    try:
        with cf.ThreadPoolExecutor(max_workers=args.episode_workers) as games:
            pending = [games.submit(run_episode, args, seed, pool, prompt_base, delays) for seed in args.seeds]
            for future in cf.as_completed(pending):
                try:
                    episodes.append(future.result())
                except BaseException:
                    pool.stopped.set()
                    raise
    finally:
        try:
            pool.close()
        finally:
            episodes.sort(key=lambda r: args.seeds.index(r['seed']))
            (args.output/'summary.json').write_text(json.dumps({'episodes':episodes,'paid_api_calls':0},indent=2)+'\n')
    if any(r['error'] for r in episodes):
        raise RuntimeError('Simulation stopped; see episode summary')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--verify-replay',type=Path)
    p.add_argument('--replay-root',type=Path)
    p.add_argument('--source',type=Path)
    p.add_argument('--suite',type=Path)
    p.add_argument('--profile',type=Path)
    p.add_argument('--strategy',type=Path)
    p.add_argument('--minimal-system-file',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--seeds',type=int,nargs='+',default=[2,5,6])
    p.add_argument('--max-frames',type=int,default=3600)
    p.add_argument('--episode-workers',type=int,choices=[1,2,3],default=3)
    p.add_argument('--controller',choices=['v2','v3','v4'],default='v3')
    p.add_argument('--quota-stop-percent',type=int,choices=range(1,81),default=50)
    p.add_argument('--latency-scale',type=float,default=1.)
    p.add_argument('--latency-seed-offset',type=int,default=42)
    a = p.parse_args()
    if a.verify_replay:
        print(json.dumps(verify_replay(a.verify_replay)))
    else:
        if not all([a.source,a.suite,a.profile,a.strategy,a.minimal_system_file,a.output]) or a.max_frames<1 or len(set(a.seeds))!=len(a.seeds):
            p.error('Simulation paths and positive max-frames required')
        run(a)
