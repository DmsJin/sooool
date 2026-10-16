"""Frozen screenshot policy, real browser/audio, live paid API verification.

Never launched by import. Native audio and browser execution continue while API
requests and image exports are pending. No chart, debug notes, or simulated time
enters a prompt. Provider's shared budget ledger enforces the cumulative $30 cap.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

from .providers import APIProvider
from .policy import prompt, parse
from .scheduler import ActionScheduler, BudgetExceeded
from .visual_env import VisualRhythmEnv, ROOT

RUNS=ROOT/'experiments/rhythm/runs'

def utc(): return datetime.now(timezone.utc).isoformat()
def file_hash(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def append(path, row):
    with Path(path).open('a') as handle: handle.write(json.dumps(row,separators=(',',':'))+'\n')

def frozen_manifest(args):
    files=['experiments/rhythm/policy.py','experiments/rhythm/scheduler.py',
           'experiments/rhythm/visual_env.py','dist/agent-bridge.js','dist/game.js',
           'experiments/rhythm/providers.py','experiments/rhythm/realtime.py']
    return {'protocol':'canvas_pixels_exact_render_audio_timestamp_v1',
            'variant':args.variant,'capacity':args.capacity,'cadence_s':args.cadence,
            'detail':args.detail,'effort':args.effort,'max_output':args.max_output,
            'commit_guard_ms':args.commit_guard_ms,'request_deadline_s':args.request_deadline,
            'speed':1,'audio_sha256':file_hash(args.audio),
            'sources':{path:file_hash(ROOT/path) for path in files}}

async def request_with_deadline(provider, text, images, deadline_s):
    """Cancel unusable inference; provider retains uncertain paid reservations."""
    return await asyncio.wait_for(provider.act(text,images),timeout=deadline_s)

async def episode(provider, args, number, frozen):
    out=RUNS/args.run/f'episode-{number:02d}'
    out.mkdir(parents=True,exist_ok=False)
    scheduler=ActionScheduler(commit_guard_ms=args.commit_guard_ms); tasks=set(); processed_logs=0; seq=0
    decisions=[]; errors=[]; dropped=0; budget_stop=False
    wall_start=time.monotonic(); utc_start=utc(); max_drift=0.; last_state=None
    async with VisualRhythmEnv(args.url,virtual=False,audio_path=args.audio,record_video_dir=out/'video') as env:
        await env.start_realtime()
        initial=await env.clock()
        baseline_audio=initial['time_s'];baseline_perf=initial['performance_ms']
        next_capture=initial['time_s']; sync_lock=asyncio.Lock()

        async def synchronize():
            """Acknowledge each actual browser event in order; never coalesce ticks."""
            nonlocal processed_logs
            log=await env.action_log()
            for entry in log[processed_logs:]:
                scheduler.acknowledge(entry['lane'],entry['time']*1000,
                    entry['actual']*1000,executed=entry['status']=='executed')
                append(out/'actions.jsonl',entry)
            processed_logs=len(log)

        async def request(obs, request_seq):
            nonlocal budget_stop
            request_wall=time.monotonic()
            image_path=out/f'obs-{request_seq:04d}.png'
            image_path.write_bytes(obs.png)
            row={'seq':request_seq,'sent_at':utc(),'observation':obs.policy_metadata(),
                 'image_sha256':hashlib.sha256(obs.png).hexdigest()}
            try:
                text=prompt(obs,args.variant)
                answer,meta=await request_with_deadline(provider,text,[obs.png],args.request_deadline)
                row.update(answer=answer,metadata=meta,arrival_at=utc(),
                           wall_latency_s=time.monotonic()-request_wall)
                actions=parse(answer,obs,args.variant)
                async with sync_lock:
                    await synchronize()
                    clock=await env.clock()
                    row['arrival_game_s']=clock['time_s']
                    if clock['state']=='playing':
                        scheduler.submit(meta.get('request_id',str(uuid.uuid4())),
                            obs.time_s*1000,actions,clock['time_s']*1000,
                            horizon_ms=1800,lanes=[0,1,2,3])
                        await env.replace_schedule([{'time':a.game_ms/1000,'lane':a.lane}
                                                   for a in scheduler.pending()])
                    else: row['discarded']='episode_finished'
            except TimeoutError as error:
                row.update(error='TimeoutError: request exceeded useful action horizon',
                    censored=True,timeout_deadline_s=args.request_deadline,
                    wall_latency_s=time.monotonic()-request_wall,arrival_at=utc(),
                    billing='uncertain reservation retained; cancellation does not prove zero charge')
                errors.append(row['error'])
            except Exception as error:
                row.update(error=type(error).__name__+': '+str(error)[:250],arrival_at=utc())
                errors.append(row['error'])
                if isinstance(error,BudgetExceeded) or 'budget' in str(error).lower():budget_stop=True
            finally:
                decisions.append(row);append(out/'decisions.jsonl',row)

        try:
            while time.monotonic()-wall_start < args.wall_timeout:
                clock=await env.clock(); last_state=clock['state']
                drift=(clock['performance_ms']-baseline_perf)/1000-(clock['time_s']-baseline_audio)
                max_drift=max(max_drift,abs(drift))
                append(out/'clock.jsonl',{'wall_utc':utc(),**clock,'relative_drift_s':drift})
                tasks={task for task in tasks if not task.done()}
                if last_state=='result':break
                if last_state!='playing' or clock['paused']:
                    errors.append('Native music stopped or game paused before completion');break
                if clock['time_s']>=next_capture:
                    next_capture=clock['time_s']+args.cadence
                    if not budget_stop and len(tasks)<args.capacity:
                        obs=await env.screenshot()
                        task=asyncio.create_task(request(obs,seq));tasks.add(task);seq+=1
                    else:dropped+=1
                await asyncio.sleep(.005)
            # Await bounded tasks; timed-out transports retain their paid reservation.
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
            async with sync_lock: await synchronize()
            result=await env.evaluator()
            if args.record_final:
                (out/'final-full.png').write_bytes((await env.screenshot(full_page=True)).png)
        finally:
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
    n=result.get('total_notes') or 0
    accuracy=result['score']/max(1,n*1000)
    unchanged=frozen_manifest(args)==frozen
    passed=(result['state']=='result' and n>0 and accuracy>=.95
            and result['counts']['miss']==0
            and unchanged and max_drift<=args.max_clock_drift)
    summary={**result,'accuracy':accuracy,'passed':passed,'episode':number,
        'mode':'live_api_native_audio','speed':1,'started_at':utc_start,'finished_at':utc(),
        'wall_s':time.monotonic()-wall_start,'maximum_relative_audio_clock_drift_s':max_drift,
        'requests':seq,'censored_request_timeouts':sum(row.get('censored',False) for row in decisions),'dropped_captures':dropped,'errors':errors,'budget_stopped':budget_stop,
        'video_path':env.video_path,'policy_unchanged':unchanged,'scheduler_rejected_late':scheduler.rejected_late,
        'scheduler_rejected_stale':scheduler.rejected_stale,
        'scheduler_rejected_refractory':scheduler.rejected_refractory}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print('REALTIME_COMPLETE '+json.dumps(summary),flush=True)
    return summary

async def main(args):
    if args.capacity<1 or args.cadence<=0 or args.request_deadline<=0:raise ValueError('Invalid cadence/capacity/deadline')
    if args.episodes<3:raise ValueError('Acceptance requires at least three complete episodes')
    frozen=frozen_manifest(args)
    folder=RUNS/args.run;folder.mkdir(parents=True,exist_ok=False)
    (folder/'frozen.json').write_text(json.dumps(frozen,indent=2))
    key=sys.stdin.readline().strip() if args.key_stdin else getpass.getpass('API key (process only): ')
    if not key:raise ValueError('Missing real API credential')
    provider=APIProvider(key,RUNS,phase='final',detail=args.detail,
                         effort=args.effort,max_output=args.max_output)
    results=[]
    try:
        for number in range(1,args.episodes+1):
            if frozen_manifest(args)!=frozen:raise RuntimeError('Frozen policy changed; verification invalid')
            results.append(await episode(provider,args,number,frozen))
            if results[-1]['budget_stopped']:break
    finally:await provider.close()
    complete=len(results)>=3 and all(row['passed'] for row in results[-3:])
    summary={'solved':complete,'required':'Three consecutive 1x complete episodes >=95% weighted accuracy, zero misses (empty presses reported separately)',
             'episodes':results,'budget':provider.ledger.snapshot(),'finished_at':utc()}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2))
    print('REALTIME_FINAL '+json.dumps({'solved':complete,'episodes':len(results),'run':args.run}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:18891')
    parser.add_argument('--audio',default='/tmp/dfjk-preview.m4a')
    parser.add_argument('--run',default='final-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    parser.add_argument('--variant',default='pixels_compact')
    parser.add_argument('--capacity',type=int,default=8)
    parser.add_argument('--cadence',type=float,default=.15)
    parser.add_argument('--episodes',type=int,default=3)
    parser.add_argument('--commit-guard-ms',type=float,default=50)
    parser.add_argument('--request-deadline',type=float,default=1.75)
    parser.add_argument('--detail',default='high')
    parser.add_argument('--effort',default='low')
    parser.add_argument('--max-output',type=int,default=512)
    parser.add_argument('--wall-timeout',type=float,default=50)
    parser.add_argument('--max-clock-drift',type=float,default=.25)
    parser.add_argument('--record-final',action='store_true')
    parser.add_argument('--key-stdin',action='store_true')
    asyncio.run(main(parser.parse_args()))
