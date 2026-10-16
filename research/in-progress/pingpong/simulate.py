"""Subscription decisions with causal sampled API latency and native replay logs.

This is a development simulator, not an official Harbor trial or realtime claim.
"""
import argparse
import base64
import concurrent.futures as cf
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('MUJOCO_GL','egl')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from core.episode import Episode,load_plugin
from core.local import Views,_header,seat_spec
from core import spec as spec_mod,score as score_mod
from core.outcome import decide
from core.sport import MatchConfig,FINISHED,UNIT_OVER,parse_action,Refused
from policy import prompt,parse
from wait_watch import make_watch,wake_reason

class Pool:
    def __init__(self,out,workers,compact=False):
        self.out=out;self.lock=threading.Lock();self.local=threading.local();self.clients=[]
        self.compact=compact
        self.pool=cf.ThreadPoolExecutor(max_workers=workers)
    def request(self,text,image,directory):
        if not hasattr(self.local,'client'):
            with self.lock:
                path=self.out/f'native_{len(self.clients)}'
                stderr=(self.out/f'native_{len(self.clients)}.stderr').open('w')
                p=subprocess.Popen(['/home/ubuntu/miniconda3/envs/latency/bin/python',str(self.out/'source'/'native_worker.py'),str(path)]+(['compact'] if self.compact else []),
                                   stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,bufsize=1)
                self.clients.append((p,stderr))
                self.local.client=p
        p=self.local.client
        p.stdin.write(json.dumps({'prompt':text,'image_b64':image,'directory':str(directory)})+'\n');p.stdin.flush()
        line=p.stdout.readline()
        if not line:raise RuntimeError('Subscription worker exited; inspect native stderr; no paid fallback')
        result=json.loads(line)
        (directory/'result.json').write_text(json.dumps(result))
        return result
    def submit(self,*args):return self.pool.submit(self.request,*args)
    def close(self):
        self.pool.shutdown(wait=True)
        for p,f in self.clients:
            p.stdin.close()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
            f.close()

def run(a):
    out=a.output;out.mkdir(parents=True,exist_ok=False)
    (out/'observations').mkdir()
    (out/'source').mkdir()
    source_hashes={}
    for path in Path(__file__).parent.glob('*.py'):
        raw=path.read_bytes();(out/'source'/path.name).write_bytes(raw)
        source_hashes[path.name]=hashlib.sha256(raw).hexdigest()
    profile=json.loads(a.profile.read_text())
    if not profile['delays_s']:raise ValueError('No valid measured API delays')
    plugin=str(ROOT/'sports/tabletennis/plugin.py');sport=load_plugin(plugin)
    cfg=MatchConfig(sport='tabletennis',format='match',seats=('A',),seed=a.seed,level=a.level,slowdown=a.slowdown,action_level='high')
    decl=spec_mod.load(plugin);m=sport.build(cfg);layer=sport.action_layer('high')
    spec=seat_spec(sport,cfg,'A',m=m,plugin=plugin)
    views=Views(sport,cfg,m,decl,True,plugin)
    ep=Episode(out/'episode.jsonl');_header(ep,sport,cfg)
    pending=[];applied=[];chunks=[];issued=0;last=-1;refused=0;dropped=0;peak=0;next_observe=0;watch=None
    menu=None
    if a.variant.startswith('geometry_'):
        from candidates import Candidates,menu_prompt
        menu=Candidates(spec,mode=a.variant)
    rng=random.Random(a.seed+481);started=time.monotonic()
    cached={};expected={};expected_blocks={};cutoff=0
    executor_mode='_executor_' in a.variant
    controller_blocked_until=0
    if a.resume_from:
        original=json.loads((a.resume_from/'protocol.json').read_text())
        for key in ('seed','level','slowdown','variant','stride','capacity','delay_scale'):
            if original[key]!=getattr(a,key):raise ValueError('Resume configuration mismatch: '+key)
        if original['profile_sha256']!=hashlib.sha256(a.profile.read_bytes()).hexdigest():raise ValueError('Resume profile mismatch')
        for line in (a.resume_from/'episode.jsonl').read_text().splitlines():
            row=json.loads(line)
            if row['ev']=='model_issued':expected[row['seq']]=row
            if row['ev']=='execution_block':expected_blocks[row['k'],row['seq']]=row
        # Only issued, logged decisions can belong to a recoverable prefix.
        # An interrupted submit may have an unlogged final worker result.
        while cutoff in expected and (a.resume_from/f'decision_{cutoff:05d}'/'result.json').exists():
            cached[cutoff]=json.loads((a.resume_from/f'decision_{cutoff:05d}'/'result.json').read_text());cutoff+=1
        print('RESUME_CONTINUOUS_PREFIX '+str(cutoff),flush=True)
    protocol={**vars(a),'profile_sha256':hashlib.sha256(a.profile.read_bytes()).hexdigest(),'api_spend_usd':0,
              'source_hashes':source_hashes,'model':'gpt-6.1-sol','mode':'subscription_sampled_delay','no_hidden_ball_state':True,
              'execution_blocking':'measured local lowering/apply wall time; pending results and observations wait while physics advances' if executor_mode else 'none'}
    (out/'protocol.json').write_text(json.dumps(protocol,default=str,indent=2))
    timing={'p50_wall_s':profile['p50_s'],'p95_wall_s':profile['p95_s'],'slowdown':a.slowdown,
            'p50_game_s':profile['p50_s']/a.slowdown,'p95_game_s':profile['p95_s']/a.slowdown,
            'observation_interval_game_s':a.stride*m.dt,'virtual_model_capacity':a.capacity}
    pool=Pool(out,a.workers,compact=bool(menu))
    def effect(body,seq,seen):
        nonlocal refused,controller_blocked_until
        action_started=time.monotonic() if executor_mode else None
        try:
            cmd=parse_action(layer,'A',body,m,{})
            low,info=layer.lower('A',cmd,None,m)
            ep.write('cmd',k=m.k,seat='A',cmd=low,seen=seen)
            result=m.apply('A',low)
            ep.write('effect',k=m.k,seq=seq,info=info,result=result)
            record={'step':m.k,'action':body,'seq':seq}
            if '_feedback_' in a.variant:
                from action_feedback import public_feedback
                record['execution_feedback']=public_feedback(info)
            applied.append(record)
            if executor_mode:
                actual_elapsed=time.monotonic()-action_started
                elapsed=actual_elapsed
                if seq<cutoff:
                    old=expected_blocks.get((m.k,seq))
                    if old is None:raise ValueError('Missing cached execution block')
                    elapsed=old['elapsed_wall_s']
                ticks=max(0,math.ceil(elapsed/a.slowdown/m.dt))
                controller_blocked_until=m.k+ticks
                ep.write('execution_block',k=m.k,seq=seq,until=controller_blocked_until,
                         elapsed_wall_s=elapsed,replay_elapsed_wall_s=actual_elapsed if seq<cutoff else None,
                         scope='native lowering/apply only; HTTP queue and transport are not included')
        except Refused as exc:
            refused+=1;ep.write('refused',k=m.k,seq=seq,reason=str(exc))
    failure=None
    try:
        while m.phase().state!=FINISHED and m.k<a.max_steps:
            if m.phase().state==UNIT_OVER:
                # No result from a completed point may control the next one.
                for req in pending:
                    req['future'].result()
                    ep.write('act_dropped',seq=req['seq'],k=m.k,why='point_over')
                    dropped+=1
                pending.clear()
                chunks.clear()
                next_observe=m.k;watch=None;controller_blocked_until=m.k
                ep.write('resume',k=m.k);m.resume()
            if m.k<controller_blocked_until:
                # Native lowering applies at the pre-catch-up step, then the
                # wall clock catches up while this controller awaits the reply.
                events=m.step()
                if events:ep.write('world_events',k=m.k,events=events)
                continue
            if watch is not None:
                public=m.observe('A');reason=wake_reason(watch,public,m.k)
                if reason:
                    ep.write('watch_wake',k=m.k,reason=reason,point=public['point'])
                    watch=None;next_observe=m.k
            for chunk in [c for c in chunks if c['due']<=m.k]:
                chunks.remove(chunk)
                effect(chunk['action'],chunk['seq'],chunk['seen'])
                if m.k<controller_blocked_until:break
            due=sorted([r for r in pending if r['due']<=m.k],key=lambda r:(r['due'],r['seq']))
            for r in due:
                if m.k<controller_blocked_until:break
                pending.remove(r)
                result=r['future'].result() # simulation clock pauses; never changes sampled latency
                ep.write('model_visible',k=m.k,seq=r['seq'],answer=result['answer'],due=r['due'],obs_step=r['obs_step'])
                if r['seq']<=last:
                    dropped+=1;continue
                try:
                    if menu:
                        choice=json.loads(result['answer'])['choice']
                        if type(choice)!=int or not 0<=choice<len(r['options']):raise ValueError('Invalid menu choice')
                        option=r['options'][choice]
                        if option['kind']=='wait':
                            body={'type':'wait'}
                            gate=make_watch(option,m.observe('A')['point'],m.k)
                            if gate is not None:
                                watch=gate
                                ep.write('watch_plan',k=m.k,seq=r['seq'],watch=gate)
                            if option.get('wait_steps'):
                                next_observe=max(next_observe,m.k+option['wait_steps'])
                                ep.write('wait_plan',k=m.k,wake_step=next_observe,seq=r['seq'])
                        elif option['kind']=='serve_bundle':
                            current=m.observe('A')
                            if chunks or current['serve']['phase']!='open':
                                dropped+=1;continue
                            first,*rest=option['actions']
                            body=dict(first['action'])
                            chunks.extend({'due':m.k+c['after_steps'],'action':c['action'],'seq':r['seq'],'seen':r['obs_step']} for c in rest)
                        else:
                            body=dict(option['action'])
                            if option.get('contact_step') is not None:
                                body['t']=(option['contact_step']-m.k)*m.dt
                                if body['t']<.04:dropped+=1;continue
                    else:body=parse(result['answer'])
                except (ValueError,KeyError,TypeError):
                    refused+=1;continue
                last=r['seq']
                if body['type']=='wait':continue
                effect(body,r['seq'],r['obs_step'])
            if m.k>=controller_blocked_until and watch is None and m.k>=next_observe and (a.variant.endswith('_chunk') or m.k%a.stride==0) and len(pending)<a.capacity:
                prep_started=time.monotonic()
                view=views.view('A',{'phase':'running','step':m.k,'t_sim':m.k*m.dt,'done':False})
                view['state']['recent_applied']=applied[-4:]
                if chunks:view['state']['known_plan']=[{'due_step':c['due'],'action':c['action']} for c in chunks]
                image=view['observation']['image_png_b64']
                (out/'observations'/f'{issued:05d}.png').write_bytes(base64.b64decode(image))
                directory=out/f'decision_{issued:05d}'
                options=menu.build(view,timing) if menu else None
                text=menu_prompt(view,options,timing,a.variant) if menu else prompt(view,spec,timing,a.variant)
                sampled=rng.choice(profile['delays_s'])*a.delay_scale
                actual_prep_s=time.monotonic()-prep_started
                prep_s=actual_prep_s
                if issued<cutoff and menu:
                    old=expected[issued]
                    if old['sampled_delay_s']!=sampled:raise ValueError('Resume delay-sample mismatch')
                    # Restore the original measured delay only for a verified cached
                    # observation/prompt prefix. Fresh decisions use fresh measurements.
                    prep_s=old['preprocessing_wall_s']
                # Explicit new menu condition includes measured camera/geometry cost.
                delay_s=sampled+(prep_s if menu else 0)
                due_step=m.k+max(1,math.ceil(delay_s/a.slowdown/m.dt))
                image_hash=hashlib.sha256(base64.b64decode(image)).hexdigest()
                if issued<cutoff:
                    old=expected[issued]
                    if old['k']!=m.k or old['due']!=due_step or old['image_sha256']!=image_hash:
                        raise ValueError('Verified-prefix replay mismatch at '+str(issued))
                    old_input=json.loads((a.resume_from/f'decision_{issued:05d}'/'input.json').read_text())
                    if old_input['params']['input'][0]['text']!=text:raise ValueError('Resume prompt mismatch')
                    directory.mkdir()
                    (directory/'input.json').write_text(json.dumps(old_input))
                    (directory/'result.json').write_text(json.dumps(cached[issued]))
                    (directory/'reused_from.json').write_text(json.dumps({'path':str(a.resume_from/f'decision_{issued:05d}')}))
                    future=cf.Future();future.set_result(cached[issued])
                else:future=pool.submit(text,image,directory)
                pending.append({'seq':issued,'due':due_step,'obs_step':m.k,'future':future,'options':options})
                ep.write('model_issued',k=m.k,seq=issued,due=due_step,sampled_delay_s=sampled,
                         image_sha256=image_hash,options=options,
                         preprocessing_wall_s=prep_s,preprocessing_in_delay=bool(menu),
                         replay_preprocessing_wall_s=actual_prep_s if issued<cutoff else None)
                issued+=1;peak=max(peak,len(pending))
                next_observe=m.k+a.stride
            events=m.step()
            if events:ep.write('world_events',k=m.k,events=events)
            if m.k%100==0:
                progress={'step':m.k,'game_s':m.k*m.dt,'scores':m.scores(),'issued':issued,'refused':refused,
                          'wall_s':time.monotonic()-started,'api_spend_usd':0}
                (out/'progress.json').write_text(json.dumps(progress));print(json.dumps(progress),flush=True)
    except BaseException as exc:
        failure=type(exc).__name__+': '+str(exc)
        (out/'failure.json').write_text(json.dumps({'error':failure,'api_spend_usd':0}))
    finally:
        pool.close()
        ep.write('end',k=m.k,reason='match_over' if m.phase().state==FINISHED else 'unfinished')
        outcome=decide(m,None,None,cfg.side_list(),cfg.side_of)
        result={'finished':m.phase().state==FINISHED,'scores':m.scores(),'winner':outcome.winner,
                'digest':m.state_digest(),'k':m.k,'seed':a.seed,'variant':a.variant,'level':a.level,'slowdown':a.slowdown,
                'calls':issued,'refused':refused,'dropped':dropped,'peak_virtual_inflight':peak,
                'wall_s':time.monotonic()-started,'failure':failure,'api_spend_usd':0,
                'continuous':score_mod.compute(m,decl,cfg.side_list())}
        (out/'summary.json').write_text(json.dumps(result,indent=2));print('SUMMARY '+json.dumps(result),flush=True)
        for renderer in sport.worker_call.__globals__.get('_LOCAL',{}).values():
            renderer.r.close()
    if failure:raise RuntimeError(failure)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--seed',type=int,default=2);p.add_argument('--level',type=int,default=1);p.add_argument('--slowdown',type=float,default=10)
    p.add_argument('--variant',default='baseline');p.add_argument('--workers',type=int,default=3);p.add_argument('--capacity',type=int,default=8)
    p.add_argument('--stride',type=int,default=10);p.add_argument('--max-steps',type=int,default=18000);p.add_argument('--delay-scale',type=float,default=1)
    p.add_argument('--resume-from',type=Path)
    run(p.parse_args())
