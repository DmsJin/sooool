"""Strictly serial, separate-file calibration of one frozen visual prompt variant.

Run manually with an interactive terminal. API key is read only via getpass.
Never writes profile.json, profile-progress.json, or any running-round inputs.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import fcntl
import getpass
import hashlib
import json
import math
from pathlib import Path
import statistics
import time
import uuid

from .providers import APIProvider
from .policy import prompt, parse
from .visual_env import ROOT, VisualRhythmEnv

RUNS=ROOT/'experiments/rhythm/runs'
TIMESTEPS=[1.4,4.5,7.6,10.6,13.7,16.8,20.,23.2]

def summarize(rows):
    complete=[row for row in rows if row.get('status')=='completed']
    values=sorted(row['latency_s'] for row in complete)
    if not values:return {'samples':0,'parse_valid':0}
    return {'samples':len(values),'parse_valid':sum(row['parse_valid'] for row in complete),
        'min_s':values[0],'median_s':statistics.median(values),
        'p95_s':values[max(0,math.ceil(.95*len(values))-1)],'max_s':values[-1]}

async def calibrate(args,key):
    if args.samples<1:raise ValueError('samples must be positive')
    if not args.variant.replace('_','').isalnum():raise ValueError('Invalid variant name')
    RUNS.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    name=f'profile-{args.variant}-{stamp}-{uuid.uuid4().hex[:6]}'
    output=RUNS/(name+'.json');images=RUNS/name;images.mkdir(exist_ok=False)
    # Process-level exclusion supplements the strictly sequential await below.
    lock=(RUNS/'variant-profiling.serial.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close();raise RuntimeError('Another variant profiler is already active')
    rows=[]
    result={'serial':True,'concurrency':1,'variant':args.variant,
        'requested_samples':args.samples,'model':'gpt-6.1-sol','tier':'ultrafast',
        'detail':args.detail,'effort':'low','max_output_tokens':512,'images_per_request':1,
        'input_protocol':'canvas_pixels_exact_render_audio_timestamp_v1',
        'started_at':datetime.now(timezone.utc).isoformat(),'rows':rows,
        'source_sha256':{file:hashlib.sha256((ROOT/file).read_bytes()).hexdigest() for file in
          ['experiments/rhythm/policy.py','experiments/rhythm/visual_env.py','dist/agent-bridge.js']},
        'limitations':['Small sample tail estimates; maximum is not a reliable P99.',
          'Strictly serial API requests; concurrent API latency is not measured.',
          'Parse validity verifies response format, not visual accuracy.']}
    def save():
        result['groups']={args.detail+'_low':summarize(rows)}
        output.write_text(json.dumps(result,indent=2))
    # Exclusive creation assures a unique result; subsequent writes update this run only.
    with output.open('x') as handle:json.dump(result,handle,indent=2)
    provider=APIProvider(key,RUNS,phase='profiling',detail=args.detail,max_output=512,effort='low')
    try:
        async with VisualRhythmEnv(args.url,virtual=True) as env:
            await env.start_virtual()
            for index in range(args.samples):
                if index and index%len(TIMESTEPS)==0:
                    await env.advance(30.1);await env.start_virtual()
                target=TIMESTEPS[index%len(TIMESTEPS)]
                await env.advance(target)
                capture_started=time.perf_counter();obs=await env.screenshot()
                capture_wall=time.perf_counter()-capture_started
                image_name=f'obs-{index:03d}.png';(images/image_name).write_bytes(obs.png)
                row={'index':index,'target_game_s':target,'obs_game_s':obs.time_s,
                    'geometry':obs.geometry,'capture_frame_age_s':obs.geometry.get('frame_age_s'),
                    'capture_wall_s':capture_wall,'image_sha256':hashlib.sha256(obs.png).hexdigest(),
                    'image_path':str(images/image_name),'images':1,'variant':args.variant,
                    'sent_at':datetime.now(timezone.utc).isoformat()}
                text=prompt(obs,args.variant)
                row['prompt_sha256']=hashlib.sha256(text.encode()).hexdigest()
                try:
                    # Deliberately NO create_task, gather, retries, or parallel API work.
                    answer,meta=await provider.act(text,[obs.png])
                    row.update(meta,answer=answer,status='completed',
                        actual_identity_verified=True,received_at=datetime.now(timezone.utc).isoformat())
                    try:
                        row['parsed']=parse(answer,obs,args.variant);row['parse_valid']=True
                    except (ValueError,TypeError) as error:
                        row.update(parsed=[],parse_valid=False,parse_error=type(error).__name__)
                    # Legacy consumer compatibility while keeping semantics explicit.
                    row['valid']=row['parse_valid']
                except Exception as error:
                    row.update(status='error',parse_valid=False,valid=False,
                        error=type(error).__name__+': '+str(error)[:250])
                    rows.append(row);result['stopped_reason']=row['error'];save()
                    print('VARIANT_PROFILE_STOP '+json.dumps({'path':str(output),'index':index,'error':row['error']}),flush=True)
                    break
                rows.append(row);save()
                print('VARIANT_PROFILE_SAMPLE '+json.dumps({'index':index,'variant':args.variant,
                    'latency_s':row['latency_s'],'parse_valid':row['parse_valid'],
                    'cost_usd':row['cost_usd'],'output':str(output)}),flush=True)
    finally:
        await provider.close()
        result['finished_at']=datetime.now(timezone.utc).isoformat()
        result['completed_samples']=sum(row.get('status')=='completed' for row in rows)
        result['budget']=provider.ledger.snapshot();save()
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    print('VARIANT_PROFILE_DONE '+json.dumps({'output':str(output),'groups':result['groups']}),flush=True)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',default='pixels_compact')
    parser.add_argument('--samples',type=int,default=8)
    parser.add_argument('--detail',choices=['high','low'],default='high')
    parser.add_argument('--url',default='http://127.0.0.1:18891')
    args=parser.parse_args()
    key=getpass.getpass('API key (process memory only): ')
    if not key:raise ValueError('Missing real API credential')
    asyncio.run(calibrate(args,key))
