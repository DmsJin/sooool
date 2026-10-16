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
from wait_watch import schedule_wait,wake_reason

def io_for_variant(variant):
    if variant.startswith('direct_'):
        from direct_io import prompt as direct_prompt,parse as direct_parse
        return direct_prompt,direct_parse
    return prompt,parse


def direct_drop_reason(request,point,phase,last):
    if phase!='playing':return 'point_over'
    if request['point']!=point:return 'point_changed'
    if request['seq']<=last:return 'stale_sequence'
    return None


def parse_direct_reply(parser,text):
    body=parser(text)  # Only documented ValueError means malformed model output.
    if not isinstance(body,dict):raise TypeError('direct_io.parse must return one action dict')
    return body

class Pool:
    def __init__(self,out,workers,compact=False,cancel_tail=False):
        self.out=out;self.lock=threading.Lock();self.local=threading.local();self.clients=[]
        self.compact=compact;self.cancel_tail=cancel_tail;self.stopping=False
        self.pool=cf.ThreadPoolExecutor(max_workers=workers)
    def request(self,text,image,directory):
        with self.lock:
            if self.stopping:raise RuntimeError('Screen tail stopped before worker request')
        if not hasattr(self.local,'client'):
            with self.lock:
                if self.stopping:raise RuntimeError('Screen tail stopped before worker startup')
                path=self.out/f'native_{len(self.clients)}'
                stderr=(self.out/f'native_{len(self.clients)}.stderr').open('w')
                p=subprocess.Popen(['/home/ubuntu/miniconda3/envs/latency/bin/python',str(self.out/'source'/'native_worker.py'),str(path)]+(['compact'] if self.compact else [])+(['--managed-tail'] if self.cancel_tail else []),
                                   stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,bufsize=1,
                                   start_new_session=self.cancel_tail)
                self.clients.append((p,stderr,path/'managed_process.json'))
                self.local.client=p
            if self.cancel_tail:
                ready=json.loads(p.stdout.readline())
                if ready!={'ready':True,'pid':p.pid}:raise RuntimeError('Native worker ready handshake failed')
        p=self.local.client
        p.stdin.write(json.dumps({'prompt':text,'image_b64':image,'directory':str(directory)})+'\n');p.stdin.flush()
        line=p.stdout.readline()
        if not line:raise RuntimeError('Subscription worker exited; inspect native stderr; no paid fallback')
        result=json.loads(line)
        (directory/'result.json').write_text(json.dumps(result))
        return result
    def submit(self,*args):return self.pool.submit(self.request,*args)
    def close(self,screen_stop=False):
        if self.cancel_tail and screen_stop:
            from worker_lifecycle import cancel_workers
            with self.lock:
                self.stopping=True;clients=list(self.clients)
            self.pool.shutdown(wait=False,cancel_futures=True)
            try:cancel_workers(clients)
            finally:
                self.pool.shutdown(wait=True)
                for p,f,_ in clients:
                    p.stdin.close();p.stdout.close();f.close()
            return
        self.pool.shutdown(wait=True)
        for p,f,_ in self.clients:
            p.stdin.close()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
            f.close()

def run(a):
    direct_mode=a.variant.startswith('direct_')
    request_prompt,response_parse=io_for_variant(a.variant)
    if direct_mode and a.fork_from:raise ValueError('Direct mode does not support menu-dependent fork replay')
    if a.screen_points < 0 or a.screen_decisions < 0 or a.screen_shots < 0:
        raise ValueError('Screening limits must be nonnegative')
    if (a.fork_from is None)!=(a.fork_seq is None) or (a.fork_seq is not None and a.fork_seq<0):
        raise ValueError('fork-from and nonnegative fork-seq must be supplied together')
    if a.fork_replay_high and not a.fork_from:raise ValueError('fork-replay-high requires fork-from')
    if a.fork_from and a.resume_from:raise ValueError('Fork and resume are mutually exclusive')
    if not 1<=a.fork_max_decisions<=120:raise ValueError('Fork decision budget must be between 1 and 120')
    if a.fork_from:
        a.screen_points=1
        a.screen_shots=1
        a.screen_decisions=min(a.screen_decisions or a.fork_max_decisions,a.fork_max_decisions)
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
    if a.fork_from:
        from core.episode import header_cfg
        source_cfg=header_cfg(json.loads((a.fork_from/'episode.jsonl').read_text().splitlines()[0]))
        if source_cfg!=cfg:raise ValueError('Fork native match configuration mismatch')
    decl=spec_mod.load(plugin);m=sport.build(cfg);layer=sport.action_layer('high')
    spec=seat_spec(sport,cfg,'A',m=m,plugin=plugin)
    if direct_mode:(out/'public_spec.json').write_text(json.dumps(spec,indent=2))
    views=Views(sport,cfg,m,decl,True,plugin)
    ep=Episode(out/'episode.jsonl');_header(ep,sport,cfg)
    pending=[];applied=[];chunks=[];issued=0;last=-1;refused=0;dropped=0;peak=0;next_observe=0;watch=None
    menu=None
    if a.variant.startswith('geometry_'):
        from candidates import Candidates,menu_prompt
        menu=Candidates(spec,mode=a.variant)
    rng=random.Random(a.seed+481);started=time.monotonic()
    cached={};expected={};expected_blocks={};cutoff=0;resume_terminal_step=None
    executor_mode=direct_mode or '_executor_' in a.variant
    controller_blocked_until=0
    if a.resume_from:
        original=json.loads((a.resume_from/'protocol.json').read_text())
        for key in ('seed','level','slowdown','variant','stride','capacity','delay_scale'):
            if original[key]!=getattr(a,key):raise ValueError('Resume configuration mismatch: '+key)
        if original['profile_sha256']!=hashlib.sha256(a.profile.read_bytes()).hexdigest():raise ValueError('Resume profile mismatch')
        from resume_timing import terminal_step
        resume_rows=[json.loads(line) for line in (a.resume_from/'episode.jsonl').read_text().splitlines()]
        resume_terminal_step=terminal_step(json.loads((a.resume_from/'summary.json').read_text()),resume_rows)
        for row in resume_rows:
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
    if a.resume_from:
        ep.write('resume_source_terminal',k=0,source=str(a.resume_from),source_terminal_step=resume_terminal_step,
                 cached_decision_count=cutoff)
    timing={'p50_wall_s':profile['p50_s'],'p95_wall_s':profile['p95_s'],'slowdown':a.slowdown,
            'p50_game_s':profile['p50_s']/a.slowdown,'p95_game_s':profile['p95_s']/a.slowdown,
            'observation_interval_game_s':a.stride*m.dt,'virtual_model_capacity':a.capacity}
    fork_provenance=None
    if a.fork_from:
        from rally_fork import setup
        high_args={'high_layer':layer,'parse_action':parse_action,'reference_factory':lambda:sport.build(cfg),'applied':applied} if a.fork_replay_high else {}
        fork_provenance=setup(a.fork_from,a.fork_seq,m,views,menu,timing,ep,**high_args)
        (out/'fork_provenance.json').write_text(json.dumps(fork_provenance,indent=2))
        started=time.monotonic()
    initial_points=sum(m.scores().values()) if a.fork_from else 0
    new_shots=0
    def advance():
        nonlocal new_shots
        events=m.step()
        new_shots+=sum(e.get('kind')=='shot' for e in events)
        return events
    pool=Pool(out,a.workers,compact=bool(menu) or direct_mode,cancel_tail='_canceltail_' in a.variant)
    from abort_stroke import AbortLifecycle
    abort_lifecycle=AbortLifecycle()
    if not direct_mode and '_recoverlift_' in a.variant:
        from recover_lift import Recovery
        recovery=Recovery()
    def effect(body,seq,seen):
        nonlocal refused,controller_blocked_until,dropped
        if not direct_mode and '_recoverlift_' in a.variant:
            public=m.observe('A');public['step']=m.k
            recovery.observe(applied)
            allowed=(recovery.delivery_allowed(public,body,applied) if '_recoverlift_point' in body else not recovery.blocked(public))
            if not allowed:
                ep.write('recoverlift_dropped',k=m.k,seq=seq,seen=seen,reason='public recovery stage, drift or installation guard',action=body)
                dropped+=1
                return
        if not direct_mode and '_abortstroke_' in a.variant and body.get('type')=='act':
            point=m.observe('A')['point']
            if abort_lifecycle.stale_act(body,point,seen):
                ep.write('abortstroke_stale_act_drop',k=m.k,seq=seq,seen=seen,point=point,
                         abort_step=abort_lifecycle.step,action=body)
                dropped+=1
                return
        if not direct_mode and '_abortstroke_' in a.variant and '_abortstroke_point' in body:
            from abort_stroke import eligible_at_delivery
            public=m.observe('A');public['step']=m.k;public['recent_applied']=applied
            if not eligible_at_delivery(public,body):
                ep.write('abortstroke_dropped',k=m.k,seq=seq,reason='public current stroke changed',action=body)
                dropped+=1
                return
        if not direct_mode and '_armready_' in a.variant and '_armready_point' in body:
            from arm_ready import eligible
            public=m.observe('A')
            if body['_armready_point']!=public['point'] or not eligible(public,applied):
                ep.write('armready_dropped',k=m.k,seq=seq,seen=seen,reason='public state changed or already prepared',action=body)
                dropped+=1
                return
        if not direct_mode and '_commitguard_' in a.variant and body.get('type')=='act':
            from commit_guard import preserve_at_delivery
            public=m.observe('A');public['step']=m.k;public['recent_applied']=applied
            if preserve_at_delivery(public,body,normal_limit=15 if '_guard15_' in a.variant else 2):
                ep.write('commit_guard_preserve',k=m.k,seq=seq,seen=seen,action=body,guard=public['commit_guard'])
                dropped+=1
                return
        action_started=time.monotonic() if executor_mode else None
        try:
            cmd=parse_action(layer,'A',body,m,{})
            low,info=layer.lower('A',cmd,None,m)
            ep.write('cmd',k=m.k,seat='A',cmd=low,seen=seen)
            result=m.apply('A',low)
            ep.write('effect',k=m.k,seq=seq,info=info,result=result)
            if not direct_mode and '_abortstroke_' in a.variant:
                abort_lifecycle.installed(body,m.observe('A')['point'],m.k,
                    low.get('type')=='slew' and low.get('rest') is True
                    and result.get('command')=='slew' and 'rejected' not in result)
            record={'step':m.k,'action':body,'seq':seq}
            if not direct_mode and '_recoverlift_' in a.variant and '_recoverlift_point' in body:
                from arm_ready import installed_prep_step
                installed=installed_prep_step(low,result,m.k) is not None
                record['_recoverlift_installed']=installed
                recovery.mark(body,installed)
            if direct_mode or '_commitguard_' in a.variant or '_abortstroke_' in a.variant:record['point']=m.observe('A')['point']
            if direct_mode or '_feedback_' in a.variant or '_abortstroke_' in a.variant:
                from action_feedback import public_feedback
                record['execution_feedback']=public_feedback(info)
            applied.append(record)
            if executor_mode:
                actual_elapsed=time.monotonic()-action_started
                from resume_timing import execution_cost
                elapsed,replay_elapsed,resume_tail=execution_cost(m.k,seq,cutoff,resume_terminal_step,
                                                                 expected_blocks,actual_elapsed,a.slowdown,m.dt)
                ticks=max(0,math.ceil(elapsed/a.slowdown/m.dt))
                controller_blocked_until=m.k+ticks
                ep.write('execution_block',k=m.k,seq=seq,until=controller_blocked_until,
                         elapsed_wall_s=elapsed,replay_elapsed_wall_s=replay_elapsed,
                         scope='native lowering/apply only; HTTP queue and transport are not included',
                         **({'resume_tail':resume_tail} if resume_tail is not None else {}))
            if not direct_mode and '_armready_point' in body:
                from arm_ready import installed_prep_step
                return installed_prep_step(low,result,m.k)
            return m.k if low.get('type')!='noop' and not result.get('rejected') else None
        except Refused as exc:
            refused+=1;ep.write('refused',k=m.k,seq=seq,reason=str(exc),
                               **({'action':body,'raw_answer':direct_answers[seq]} if direct_mode else {}))
    direct_answers={}
    failure=None;screen_reason=None
    try:
        while m.phase().state!=FINISHED and m.k<a.max_steps:
            if a.screen_points and sum(m.scores().values())-initial_points>=a.screen_points:
                screen_reason='point_limit'
            elif a.screen_shots and new_shots>=a.screen_shots:
                screen_reason='shot_limit'
            elif a.screen_decisions and issued>=a.screen_decisions:
                screen_reason='decision_limit'
            if screen_reason:
                # Drain issued work without exposing new actions or advancing physics.
                if '_canceltail_' in a.variant:
                    for req in pending:
                        req['future'].cancel()
                        ep.write('act_dropped',seq=req['seq'],k=m.k,why='screen_unused_tail_cancel')
                        dropped+=1
                else:
                    for req in pending:req['future'].result()
                ep.write('screen_stop',k=m.k,reason=screen_reason,issued=issued)
                break
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
                events=advance()
                if events:ep.write('world_events',k=m.k,events=events)
                continue
            if watch is not None:
                public=m.observe('A');reason=wake_reason(watch,public,m.k)
                if reason:
                    ep.write('watch_wake',k=m.k,reason=reason,point=public['point'])
                    watch=None;next_observe=m.k
            for chunk in [c for c in chunks if c['due']<=m.k]:
                chunks.remove(chunk)
                if 'point' in chunk and chunk['point']!=m.observe('A')['point']:
                    ep.write('armready_followup_dropped',k=m.k,seq=chunk['seq'],reason='point_changed')
                    continue
                effect(chunk['action'],chunk['seq'],chunk['seen'])
                if m.k<controller_blocked_until:break
            due=sorted([r for r in pending if r['due']<=m.k],key=lambda r:(r['due'],r['seq']))
            for r in due:
                if m.k<controller_blocked_until:break
                pending.remove(r)
                result=r['future'].result() # simulation clock pauses; never changes sampled latency
                ep.write('model_visible',k=m.k,seq=r['seq'],answer=result['answer'],due=r['due'],obs_step=r['obs_step'])
                if direct_mode:
                    reason=direct_drop_reason(r,m.observe('A')['point'],m.phase().state,last)
                    if reason:
                        ep.write('act_dropped',k=m.k,seq=r['seq'],why=reason,
                                 observed_point=r['point'],current_point=m.observe('A')['point'])
                        dropped+=1;continue
                    last=r['seq']
                    direct_answers[r['seq']]=result['answer']
                    try:body=parse_direct_reply(response_parse,result['answer'])
                    except ValueError as exc:
                        refused+=1;ep.write('refused',k=m.k,seq=r['seq'],reason=str(exc),
                                           stage='direct_parse',raw_answer=result['answer'])
                        continue
                    if body['type']!='wait':effect(body,r['seq'],r['obs_step'])
                    continue
                if r['seq']<=last:
                    dropped+=1;continue
                try:
                    if menu:
                        choice=json.loads(result['answer'])['choice']
                        if type(choice)!=int or not 0<=choice<len(r['options']):raise ValueError('Invalid menu choice')
                        option=r['options'][choice]
                        if option['kind']=='wait':
                            body={'type':'wait'}
                            next_observe,watch=schedule_wait(next_observe,watch,option,m.observe('A')['point'],m.k,
                                                            latest='_latestwait_' in a.variant)
                            if option.get('watch_for') is not None:
                                ep.write('watch_plan',k=m.k,seq=r['seq'],watch=watch)
                            if option.get('wait_steps'):
                                ep.write('wait_plan',k=m.k,wake_step=next_observe,seq=r['seq'])
                        elif option['kind']=='armready_bundle':
                            from arm_ready import bundle_first,bundle_followups
                            current=m.observe('A');body=bundle_first(option,m.k)
                            last=r['seq']
                            if chunks or body is None or body['_armready_point']!=current['point']:
                                dropped+=1;continue
                            took_effect=effect(body,r['seq'],r['obs_step'])
                            chunks.extend(bundle_followups(option,took_effect,current['point'],r['seq'],r['obs_step']))
                            continue
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
                    else:body=response_parse(result['answer'])
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
                text=menu_prompt(view,options,timing,a.variant) if menu else request_prompt(view,spec,timing,a.variant)
                if direct_mode:
                    (out/'observations'/f'{issued:05d}.prompt.txt').write_text(text)
                from partial_evidence import snapshot_bytes,digest
                image_hash=hashlib.sha256(base64.b64decode(image)).hexdigest()
                parent_raw=snapshot_bytes(issued,m.k,view['state'],image_hash,text)
                # Exclusive creation: immutable evidence of what the controller offered,
                # including work canceled before a worker records a turn/start input.
                with (out/'observations'/f'{issued:05d}.json').open('xb') as parent_file:parent_file.write(parent_raw)
                parent_hash=digest(parent_raw);prompt_hash=digest(text.encode())
                sampled=rng.choice(profile['delays_s'])*a.delay_scale
                actual_prep_s=time.monotonic()-prep_started
                prep_s=actual_prep_s
                if issued<cutoff and (menu or direct_mode):
                    old=expected[issued]
                    if old['sampled_delay_s']!=sampled:raise ValueError('Resume delay-sample mismatch')
                    # Restore the original measured delay only for a verified cached
                    # observation/prompt prefix. Fresh decisions use fresh measurements.
                    prep_s=old['preprocessing_wall_s']
                # Explicit new menu condition includes measured camera/geometry cost.
                delay_s=sampled+(prep_s if menu or direct_mode else 0)
                due_step=m.k+max(1,math.ceil(delay_s/a.slowdown/m.dt))
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
                pending.append({'seq':issued,'due':due_step,'obs_step':m.k,'future':future,'options':options,
                                **({'point':view['state']['point']} if direct_mode else {})})
                ep.write('model_issued',k=m.k,seq=issued,due=due_step,sampled_delay_s=sampled,
                         image_sha256=image_hash,options=options,
                         parent_observation_sha256=parent_hash,prompt_sha256=prompt_hash,
                         preprocessing_wall_s=prep_s,preprocessing_in_delay=bool(menu) or direct_mode,
                         replay_preprocessing_wall_s=actual_prep_s if issued<cutoff else None)
                issued+=1;peak=max(peak,len(pending))
                next_observe=m.k+a.stride
            events=advance()
            if events:ep.write('world_events',k=m.k,events=events)
            if m.k%100==0:
                progress={'step':m.k,'game_s':m.k*m.dt,'scores':m.scores(),'issued':issued,'refused':refused,
                          'wall_s':time.monotonic()-started,'api_spend_usd':0}
                (out/'progress.json').write_text(json.dumps(progress));print(json.dumps(progress),flush=True)
    except BaseException as exc:
        failure=type(exc).__name__+': '+str(exc)
        (out/'failure.json').write_text(json.dumps({'error':failure,'api_spend_usd':0}))
    finally:
        if screen_reason and '_canceltail_' in a.variant:
            try:pool.close(screen_stop=True)
            except BaseException as exc:
                failure=failure or 'Worker cleanup: '+type(exc).__name__+': '+str(exc)
        else:pool.close()
        ep.write('end',k=m.k,reason='match_over' if m.phase().state==FINISHED else screen_reason or 'unfinished')
        outcome=decide(m,None,None,cfg.side_list(),cfg.side_of)
        result={'finished':m.phase().state==FINISHED,'scores':m.scores(),'winner':outcome.winner if m.phase().state==FINISHED and not a.fork_from else None,
                'branched':bool(a.fork_from),'fork_provenance':fork_provenance,'new_shots':new_shots,
                'screened':bool(screen_reason and not failure),'screen_stop_reason':screen_reason,
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
    p.add_argument('--fork-max-decisions',type=int,default=30);p.add_argument('--fork-replay-high',action='store_true');p.add_argument('--fork-from',type=Path);p.add_argument('--fork-seq',type=int);p.add_argument('--screen-shots',type=int,default=0)
    p.add_argument('--screen-points',type=int,default=0);p.add_argument('--screen-decisions',type=int,default=0)
    run(p.parse_args())
