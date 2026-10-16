"""Six wall-clock Asterix episodes, frozen compact_spaced_hop, shared USD20 guard."""
import argparse
import base64
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import statistics
import threading
import time

from profile_policy_latency import MODEL, TIER, OUTPUT_LIMIT, PROMPT_HASH, payload, stats
from realtime_policy_core import BudgetStop, HopController, RealtimeBudget

ORDER = [(10, 2), (7, 2), (5, 2), (5, 5), (7, 5), (10, 5)]
FRAMES = 1200


def write(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2)+'\n')
    temp.replace(path)


def realtime_prompt(original, slowdown):
    pairs = [
        ('The virtual game runs at 7.5 raw frames per second, one eighth normal speed.',
         f'The game advances continuously at {60/slowdown:.6g} raw frames per wall-clock second, {slowdown} times slower than normal 60 FPS.'),
        ('A command becomes available only after a sampled response delay.',
         'A command becomes available only after your complete API response arrives.'),
        ('Your actual wall-clock thinking time does not advance this simulation.',
         'The game continues to advance while your API response is computed.'),
    ]
    text = original
    for old, new in pairs:
        if text.count(old) != 1:
            raise ValueError('Frozen prompt does not match expected source')
        text = text.replace(old, new)
    text, n = re.subn(r'Measured Ultrafast complete-response delay: mean \d+ ms, median \d+ ms, P95 \d+ ms\.',
                      'Measured API complete-response delay: mean 1224 ms, median 1201 ms, P95 1841 ms.', text)
    if n != 1:
        raise ValueError('Missing frozen latency paragraph')
    return text


def suffix(frame, images, action, applied):
    text = f'Current observation frame: {frame}. Image frames: {[f for f,_ in images]}. Current held action: {action}.\n'
    text += 'Applied commands, oldest first, age_in_raw_frames:action: '
    text += ','.join(str(frame-x['frame'])+':'+str(x['action']) for x in applied[-8:])+'.\n'
    if len(text.encode()) > 512:
        raise ValueError('Dynamic suffix exceeds preflight token envelope')
    return text


def png(obs):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(obs).resize((224,224), Image.Resampling.BILINEAR).save(buf, format='PNG')
    return buf.getvalue()


def content(text, images):
    return [{'role':'user', 'content':[{'type':'input_text', 'text':text}]+[
        {'type':'input_image', 'detail':'low', 'image_url':'data:image/png;base64,'+base64.b64encode(im).decode()}
        for im in images]}]


class API:
    def __init__(self, key, budget, input_limit):
        self.headers = {'Authorization':'Bearer '+key, 'Content-Type':'application/json'}
        self.budget, self.input_limit = budget, input_limit
        self.local = threading.local()
        self.sessions = []
        self.lock = threading.Lock()

    def call(self, ticket, seq, frame, images, text, captured):
        import requests
        row = {'seq':seq, 'obs_frame':frame, 'captured_monotonic':captured,
               'image_sha256':[hashlib.sha256(im).hexdigest() for _,im in images],
               'prompt':text, 'status':'error'}
        usage = None
        started = time.perf_counter()
        ttft = None
        response = None
        try:
            if not hasattr(self.local, 'http'):
                self.local.http = requests.Session()
                with self.lock:
                    self.sessions.append(self.local.http)
            body = payload({'input':content(text, [im for _,im in images])})
            with self.local.http.post('https://api.openai.com/v1/responses', headers=self.headers,
                                      json=body, stream=True, timeout=(10,45)) as r:
                if r.status_code != 200:
                    raise RuntimeError('HTTP '+str(r.status_code))
                for line in r.iter_lines(chunk_size=1):
                    if not line.startswith(b'data: ') or line[6:] == b'[DONE]':
                        continue
                    event = json.loads(line[6:])
                    if event.get('type') == 'response.output_text.delta' and ttft is None:
                        ttft = time.perf_counter()-started
                    if event.get('type') in ('response.completed','response.failed','response.incomplete'):
                        response = event['response']
                        usage = response.get('usage')
                        break
            if not response:
                raise RuntimeError('Missing terminal API response')
            answer = ''.join(c.get('text','') for x in response.get('output',[]) if x['type']=='message'
                             for c in x.get('content',[]) if c['type']=='output_text').strip()
            valid = answer in tuple(str(i) for i in range(9))
            row.update(status=response['status'], answer=answer, usage=usage, action_valid=valid,
                       model=response.get('model'), tier=response.get('service_tier'))
            if row['model'] != MODEL or row['tier'] != TIER:
                raise RuntimeError('Unexpected model or service tier')
            if valid and row['status'] == 'completed':
                row['chosen'] = int(answer)
        except Exception as exc:
            row.update(status='error', error_type=type(exc).__name__,
                       error=str(exc) if isinstance(exc,RuntimeError) else 'Transport or parsing error')
        finally:
            row.update(request_s=time.perf_counter()-started, ttft_s=ttft,
                       completed_monotonic=time.perf_counter())
            row['accounted_usd'] = self.budget.settle(ticket, usage, self.input_limit)/1e6
        return row

    def close(self):
        for session in self.sessions:
            session.close()
        self.headers.clear()


def video(path, snapshots, seed, slowdown, score):
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    font_path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    font = ImageFont.truetype(str(font_path),15) if font_path.exists() else ImageFont.load_default()
    names = ['NOOP','UP','RIGHT','LEFT','DOWN','UPRIGHT','UPLEFT','DOWNRIGHT','DOWNLEFT']
    writer = imageio_ffmpeg.write_frames(str(path),(320,480),fps=60,codec='libx264',
                                        pix_fmt_out='yuv420p',macro_block_size=1,
                                        output_params=['-crf','18','-preset','veryfast','-movflags','+faststart'])
    writer.send(None)
    try:
        for frame,obs,current,lives,action in snapshots:
            canvas = Image.new('RGB',(320,480),(13,17,23))
            canvas.paste(Image.fromarray(obs).resize((320,420),Image.Resampling.NEAREST),(0,60))
            draw = ImageDraw.Draw(canvas)
            draw.text((7,2),f'{slowdown}x slow | seed {seed} | final {int(score)}',font=font,fill=(120,210,255))
            draw.text((7,21),f'game {frame/60:.2f}s | score {int(current)}',font=font,fill='white')
            draw.text((7,40),f'lives {lives} | {names[action]}',font=font,fill=(255,170,100))
            writer.send(np.asarray(canvas))
    finally:
        writer.close()


def episode(out, slowdown, seed, base, key, budget, input_limit, update):
    import gymnasium as gym
    import ale_py
    gym.register_envs(ale_py)
    root = out/f'slow{slowdown}-seed{seed}'
    root.mkdir()
    (root/'prompt.txt').write_text(base)
    fps = 60/slowdown
    env = gym.make('ALE/Asterix-v5',render_mode='rgb_array',obs_type='rgb',frameskip=1,
                   repeat_action_probability=0.,full_action_space=False,mode=0,difficulty=0,
                   max_num_frames_per_episode=108000)
    obs,info = env.reset(seed=seed)
    noops = int(env.unwrapped.np_random.integers(1,31))
    for _ in range(noops):
        obs,_,done,truncated,info = env.step(0)
        if done or truncated:
            obs,info = env.reset()
    assert env.unwrapped.get_action_meanings()==['NOOP','UP','RIGHT','LEFT','DOWN','UPRIGHT','UPLEFT','DOWNRIGHT','DOWNLEFT']
    api = API(key,budget,input_limit)
    pool = ThreadPoolExecutor(max_workers=8)
    pending, records, snapshots, lags = {}, [], [], []
    controller = HopController()
    window = deque(maxlen=9)
    score = 0.
    calls = drops = executed = peak = 0
    status = 'horizon'
    start = time.perf_counter()
    before = budget.snapshot()['accounted_usd']
    steps = (root/'steps.jsonl').open('w')
    requests_log = (root/'requests.jsonl').open('w')
    try:
        for frame in range(FRAMES):
            target = start+frame/fps
            time.sleep(max(0,target-time.perf_counter()))
            now = time.perf_counter()
            lags.append(max(0,now-target))
            completed = []
            for future in list(pending):
                if future.done():
                    row = future.result()
                    del pending[future]
                    row['capture_to_apply_s'] = now-row['captured_monotonic']
                    completed.append(row)
            ready = [r for r in completed if r['status']=='completed' and r.get('action_valid')]
            old = controller.last
            action = controller.advance(frame,ready)
            for row in completed:
                row['disposition'] = ('applied' if row['seq']==controller.last and controller.last>old
                                      else 'stale_or_superseded' if row in ready else 'failed')
                row['completion_observed_frame'] = frame
                records.append(row)
                requests_log.write(json.dumps(row)+'\n')
            requests_log.flush()
            if any(r['status']!='completed' or not r.get('action_valid') for r in completed):
                status = 'api_error'
                break
            if budget.stopped:
                status = 'budget_stop'
                break
            if frame%4==0:
                window.append((frame,png(obs)))
                n = len(window)
                images = [window[i] for i in sorted({0,max(0,n-3),n-1})]
                if len(pending)<8:
                    text = base+suffix(frame,images,action,controller.applied)
                    bound = input_limit*15+OUTPUT_LIMIT*60
                    ticket = budget.reserve(bound)
                    captured = time.perf_counter()
                    future = pool.submit(api.call,ticket,calls,frame,images,text,captured)
                    pending[future] = calls
                    calls += 1
                    peak = max(peak,len(pending))
                else:
                    drops += 1
            snapshots.append((frame,obs.copy(),score,info.get('lives'),action))
            obs,reward,done,truncated,info = env.step(action)
            score += reward
            executed = frame+1
            steps.write(json.dumps({'frame':frame,'action':action,'reward':reward,'score':score,
                                    'lives':info.get('lives'),'wall_s':time.perf_counter()-start})+'\n')
            if frame%60==0:
                steps.flush()
                update({'slowdown':slowdown,'seed':seed,'game_seconds':executed/60,'score':score,
                        'lives':info.get('lives'),'requests':calls,'inflight':len(pending),
                        'wall_seconds':time.perf_counter()-start,**budget.snapshot()})
            if done or truncated:
                status = 'natural_end'
                break
    except BudgetStop:
        status = 'budget_stop'
    except Exception as exc:
        status = 'internal_error'
        write(root/'error.json',{'type':type(exc).__name__})
    finally:
        time.sleep(max(0,start+executed/fps-time.perf_counter()))
        elapsed = time.perf_counter()-start
        for future in as_completed(pending):
            row = future.result()
            row['disposition'] = 'after_episode'
            records.append(row)
            requests_log.write(json.dumps(row)+'\n')
        pool.shutdown(wait=True)
        api.close()
        steps.close()
        requests_log.close()
        env.close()
    if any(r['status']!='completed' or not r.get('action_valid') for r in records) and status=='horizon':
        status = 'api_error_during_drain'
    summary = {'slowdown':slowdown,'seed':seed,'score':score,'frames':executed,
               'game_seconds':executed/60,'lives':info.get('lives'),'reset_noops':noops,
               'status':status,'wall_seconds':elapsed,'wall_including_drain':time.perf_counter()-start,
               'target_fps':fps,'actual_fps':executed/elapsed if elapsed else None,
               'max_frame_lag_s':max(lags) if lags else None,'peak_inflight':peak,'drops':drops,
               'calls':calls,'episode_accounted_usd':budget.snapshot()['accounted_usd']-before,
               'latency':stats(records),'video_playback_fps':60,
               'timing_valid':bool(lags) and max(lags)<0.25}
    write(root/'actions.json',controller.applied)
    write(root/'summary.json',summary)
    if snapshots:
        video(root/'game-normal-speed.mp4',snapshots,seed,slowdown,score)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-prompt',type=Path,required=True)
    parser.add_argument('--sample-inputs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--budget-usd',type=Decimal,default=Decimal('20'))
    parser.add_argument('--prior-results',type=Path)
    parser.add_argument('--run-paid',action='store_true')
    parser.add_argument('--prompt-for-key',action='store_true')
    args = parser.parse_args()
    original = args.frozen_prompt.read_text()
    if hashlib.sha256(original.encode()).hexdigest()!=PROMPT_HASH:
        raise SystemExit('Wrong original policy prompt')
    bases = {slow:realtime_prompt(original,slow) for slow in (10,7,5)}
    if not Decimal('0')<args.budget_usd<=Decimal('20'):
        raise SystemExit('Budget must be at most USD20')
    if not args.run_paid:
        print(json.dumps({'status':'offline_preflight_ok','order':ORDER,'max_frames_each':FRAMES,
                          'max_calls_each':FRAMES//4,'wall_seconds_total':880,'max_inflight':8,
                          'budget_usd':str(args.budget_usd),'api_calls':0}))
        return
    prior = 0
    if args.prior_results:
        previous = json.loads((args.prior_results/'summary.json').read_text())
        if previous['unsettled_reserved_usd']!=0:
            raise SystemExit('Previous paid requests still unsettled')
        prior = int(Decimal(str(previous['accounted_usd']))*1_000_000)
    key = getpass.getpass('API key (memory only): ') if args.prompt_for_key else os.environ.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit('Missing API key; no calls made')
    import requests
    args.output.mkdir(parents=True,exist_ok=False)
    # Count each static prefix with three low-detail224 images. Every dynamic
    # suffix is limited to512 UTF8 bytes;1024 additional tokens cover it with slack.
    sample = json.loads(args.sample_inputs.read_text())['samples'][0]['input'][0]['content'][1:]
    counts = {}
    with requests.Session() as http:
        for slow,base in bases.items():
            body = {'model':MODEL,'input':[{'role':'user','content':[{'type':'input_text','text':base}]+sample}]}
            r = http.post('https://api.openai.com/v1/responses/input_tokens',
                          headers={'Authorization':'Bearer '+key},json=body,timeout=(10,30))
            if r.status_code!=200:
                raise SystemExit('Token-count HTTP '+str(r.status_code)+'; no inference dispatched')
            counts[slow] = r.json()['input_tokens']
    input_limit = max(counts.values())+1024
    if input_limit>=8192:
        raise SystemExit('Unexpectedly large input; no inference dispatched')
    budget = RealtimeBudget(args.output/'budget.jsonl',int(args.budget_usd*1_000_000),prior)
    protocol = {'policy':'compact_spaced_hop','original_prompt_sha256':PROMPT_HASH,
                'prompt_changes':'Only real wall-clock semantics, slowdown FPS, and measured delay paragraph.',
                'model':MODEL,'tier':TIER,'effort':'low','max_output_tokens':OUTPUT_LIMIT,
                'order':ORDER,'max_frames_each':FRAMES,'normal_game_fps':60,'observation_stride':4,
                'history_span_raw_frames':32,'max_images':3,'max_inflight':8,'episodes_run_in_parallel':1,
                'token_prefix_counts':counts,'input_token_reservation_limit':input_limit,
                'prior_accounted_usd':prior/1e6,'budget_usd':str(args.budget_usd),
                'latency_source':'paid24-request concurrent transfer probe: mean1.224s,p501.201s,p951.841s',
                'uses_sampled_delays':False,'clock':'perf_counter frame deadlines; never wait for a model response in game loop',
                'image_preprocessing':'224x224 bilinear PNG; API low detail',
                'transport':'persistent HTTPS SSE per worker; no retries'}
    write(args.output/'protocol.json',protocol)
    state = {'status':'running','episodes':[],'current':None,**budget.snapshot()}
    def update(current=None):
        state.update(current=current,updated_at_epoch=time.time(),**budget.snapshot())
        write(args.output/'progress.json',state)
    update()
    print('OUTPUT '+str(args.output),flush=True)
    print('PREFLIGHT '+json.dumps({'input_limit':input_limit,'reservation_per_request_usd':(input_limit*15+OUTPUT_LIMIT*60)/1e6,'prior_usd':prior/1e6}),flush=True)
    try:
        for slow,seed in ORDER:
            result = episode(args.output,slow,seed,bases[slow],key,budget,input_limit,update)
            state['episodes'].append(result)
            update()
            print('EPISODE '+json.dumps(result),flush=True)
            if result['status'] not in ('horizon','natural_end') or not result['timing_valid'] or budget.stopped:
                state['status'] = 'stopped_requires_attention'
                break
        else:
            state['status'] = 'complete'
    except BaseException as exc:
        state.update(status='stopped_requires_attention', error_type=type(exc).__name__)
        raise
    finally:
        key = None
        update()
        write(args.output/'summary.json',state)
        print('DONE '+json.dumps(state),flush=True)


if __name__=='__main__':
    main()
