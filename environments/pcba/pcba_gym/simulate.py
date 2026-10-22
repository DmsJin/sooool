"""Subscription development under a virtual clock and resampled measured reply delays.

Every decision is a fresh subscription inference on the actual rendered frames. Physics
advances only in the trusted event loop: a reply becomes usable at its capture time plus
a delay resampled from a measured profile. If the actual inference is still running at
that virtual time, the virtual clock waits (computation consumes wall time, not virtual
time). Results are DEVELOPMENT evidence, never a realtime or 1x claim.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import hashlib
import json
import math
import time
import numpy as np
from PIL import Image
from runtime.evaluation import recording
from runtime.options import positive_float
from .environment import PCBATestCell
from .scene import BOARD_COUNT
from .runner import ROOT, POLICY, freeze, write, save_report
from .latency import stats
from .pipeline import (CONTROL_DT, OUTPUT_MODES, SCHEDULES, parse_pipeline, rejection, request_due, encode_png,
    pipeline_prompt, pipeline_schema, latency_summary, awaiting_result, top_calibration_text, wrist_calibration_text, CAMERA_MODES, render_cameras, capture, parse_image_size, infer_timed, save_states, add_latency_arguments)


def load_latency_profile(path):
    """Capture-to-reply seconds from a retained run directory, or a {'samples_s': [...]} JSON file."""
    path=Path(path).resolve();samples=[];kind=None;measured=True
    if path.is_dir():
        report=path/'report.json'
        if report.exists():
            calls=json.loads(report.read_text()).get('calls',[])
            samples=[c['completed_wall']-c['capture_wall'] for c in calls
                     if 'model_wall_seconds' in c and 'completed_wall' in c and 'capture_wall' in c]
            kind='capture_to_reply_from_report'
        if not samples:
            samples=[json.loads(f.read_text())['meta']['wall_seconds'] for f in sorted(path.glob('call-*/model/result.json'))]
            kind='native_request_wall_seconds_without_capture_overhead'
    else:
        data=json.loads(path.read_text());samples=[float(v) for v in data['samples_s']]
        kind=data.get('kind','profile_file');measured=data.get('measured')
    if len(samples)<5 or not all(math.isfinite(v) and v>0 for v in samples):
        raise ValueError(f'Latency profile needs at least 5 positive samples: {path}')
    digest=hashlib.sha256(json.dumps(samples).encode()).hexdigest()
    return samples,{'source':str(path),'kind':kind,'measured':measured,'n':len(samples),'samples_sha256':digest,'summary':stats(samples)}


class VirtualRecorder:
    """Evaluator-only state samples on the virtual timeline (no online replay rendering)."""
    def __init__(self,env,out,interval=.1):
        self.env=env;self.out=out;self.frames=[];self.states=[];self.next_frame=-1.;self.interval=interval

    def sample(self,force=False):
        now=float(self.env.data.time)
        if not force and now<self.next_frame:return
        state={k:getattr(self.env.data,k).copy() for k in ('qpos','qvel','ctrl','eq_active')}
        state['geom_rgba']=self.env.model.geom_rgba.copy();self.states.append(state)
        # wall_time carries VIRTUAL seconds so exported video follows the simulated clock.
        self.frames.append({'path':f'frames/{len(self.frames):05d}.png','simulation_time_s':now,'wall_time':now})
        self.next_frame=now+self.interval


def simulate_pipeline(output,*,profile,latency_scale=1.,latency_seed=0,concurrency=1,sim_duration=150.,max_calls=24,
                      max_wall=1800.,ttl=12.,request_interval=.75,seed=0,layout='loop',camera_mode='top',
                      image_size=(640,480),output_mode='lean',schedule='stagger',expected_latency=8.,
                      transport_tuning=True,service_tier='default',continue_after_deadline=False,top_calibration=False,effort='low'):
    from runtime.subscription import SubscriptionClient
    if concurrency not in (1,2,4):raise ValueError('concurrency must be 1, 2 or 4')
    if layout not in ('stopped','loop') or camera_mode not in CAMERA_MODES:raise ValueError('Unknown layout or camera mode')
    if output_mode not in OUTPUT_MODES or schedule not in SCHEDULES:raise ValueError('Unknown output mode or schedule')
    if service_tier not in ('default','priority'):raise ValueError('Unsupported service tier')
    if not 0<sim_duration<=600 or not 1<=max_calls<=400 or not 0<ttl<=15 or not 0<latency_scale<=4 or request_interval<.25:
        raise ValueError('Invalid simulation limits')
    width,height=parse_image_size('x'.join(map(str,image_size)))
    cameras=render_cameras(camera_mode)
    samples,provenance=load_latency_profile(profile)
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    config={'mode':'subscription_simulation_virtual_clock','evidence':'development only; not a realtime or 1x result',
            'latency_profile':provenance,'latency_scale':latency_scale,'latency_seed':latency_seed,
            'latency_sampling':'IID whole-sample resampling of capture-to-reply seconds, drawn at capture; never shown to the actor',
            'concurrency':concurrency,'sim_duration_s':sim_duration,'max_calls':max_calls,'max_wall_s':max_wall,
            'observation_ttl_s':ttl,'request_interval_s':request_interval,'seed':seed,'layout':layout,
            'policy_cameras':list(cameras),'image_size':[width,height],'png_compress_level':1,'output_mode':output_mode,
            'schedule':schedule,'expected_latency_s':expected_latency,'top_calibration':top_calibration,'model':'gpt-6.1-sol','effort':effort,'service_tier':service_tier,
            'transport':{'quota_check_every_calls':10 if transport_tuning else 1,'prestarted_threads':transport_tuning},
            'continue_after_deadline':continue_after_deadline,'control_dt_s':CONTROL_DT,'execution_lanes':1}
    freeze(out,config)
    manifest=json.loads((out/'manifest.json').read_text())
    manifest.update({'mode':'subscription_simulation_virtual_clock','evidence':config['evidence']});write(out/'manifest.json',manifest)
    if layout=='loop':
        from .loop import PCBALoopCell
        env=PCBALoopCell(seed=seed,asset_dir=out/'assets')
    else:env=PCBATestCell(seed=seed,asset_dir=out/'assets')
    (out/'scene.xml').write_text(env.xml)
    calibration=top_calibration_text(env.model,width,height) if top_calibration and 'top' in cameras else None
    wrist_calibration=wrist_calibration_text(env.model,width,height) if camera_mode=='adaptive' else None
    rng=np.random.default_rng(latency_seed)
    clients=[];pending=[];candidates=[];calls=[];chunks=[];events=[];memory='';previous=None
    revision=0;parent_success=True;latest_selected=-1;active=None;error=None;stop_reason='sim_duration'
    pool=None;recorder=VirtualRecorder(env,out);next_request=-math.inf;wall_started=time.monotonic();paused_wall=0.
    t0=float(env.data.time)
    def now():return float(env.data.time)
    def event(kind,**fields):events.append({'sim_s':now(),'kind':kind,**fields})

    def finish_chunk():
        nonlocal active,parent_success,previous
        execution=active['execution'];execution['last_receipt']=execution['commands'][-1]['receipt'] if execution['commands'] else None
        parent_success=execution['accepted_commands']==execution['requested_commands']
        row={k:v for k,v in active.items() if k not in ('actions','log')};row['finished_s']=now();chunks.append(row)
        active['log'].close();write(out/f'chunk-{active["revision"]:03d}.json',row)
        previous={k:v for k,v in execution.items() if k!='commands'}
        event('chunk_completed',revision=active['revision'],accepted=execution['accepted_commands'],requested=execution['requested_commands'])
        active=None

    try:
        env.observe(cameras=cameras,width=width,height=height)
        for i in range(concurrency):
            clients.append(SubscriptionClient(output=out/f'worker-{i}',output_schema=pipeline_schema(output_mode),
                system=(POLICY/'system.txt').read_text(),auth_only_home=True,record_reasoning=False,service_tier=service_tier,effort=effort,
                quota_every=10 if transport_tuning else 1,prestart=transport_tuning))
        pool=ThreadPoolExecutor(max_workers=concurrency,thread_name_prefix='pcba-sim-infer')
        recorder.sample(force=True)
        while now()-t0<sim_duration:
            if time.monotonic()-wall_started>max_wall:stop_reason='max_wall';break
            if active and active['index']>=len(active['actions']):finish_chunk()
            # Replies become usable only at their sampled virtual readiness time.
            for packet in sorted([p for p in pending if p['ready_s']<=now()+1e-9],key=lambda p:p['ready_s']):
                pending.remove(packet);row=packet['row'];waited=time.monotonic()
                try:
                    answer,meta=packet['future'].result()
                    row.update({'virtual_pause_wall_s':time.monotonic()-waited,'native_wall_seconds':meta['wall_seconds'],
                        'model_wall_seconds':meta['transport_finished_wall']-meta['transport_started_wall'],
                        'token_usage':meta['token_usage'],'transport_stages_s':meta.get('stages_s'),'completed_s':now()})
                    decision,actions=parse_pipeline(answer);packet.update({'decision':decision,'actions':actions})
                    row['summary']=decision['summary'];candidates.append(packet)
                    event('reply_ready',sequence=packet['sequence'],parent_revision=packet['parent_revision'])
                except (ValueError,TypeError) as exc:row['discard_reason']='invalid_output';row['detail']=str(exc);row['completed_s']=now()
                except Exception as exc:row['discard_reason']='request_error';row['detail']=str(exc);row['completed_s']=now()
                paused_wall+=time.monotonic()-waited
            for packet in list(candidates):
                if packet['parent_revision']!=revision or packet['sequence']<=latest_selected:
                    packet['row']['discard_reason']='superseded_parent_or_sequence';candidates.remove(packet)
            if active is None and candidates:
                observation=env.observe()
                for packet in sorted(candidates,key=lambda p:p['sequence'],reverse=True):
                    # Virtual seconds stand in for both clocks of the realtime gate.
                    reason=rejection(packet,revision=revision,parent_success=parent_success,latest_selected=latest_selected,
                        observation=observation,wall_now=now(),ttl=ttl)
                    candidates.remove(packet)
                    if reason:
                        packet['row']['discard_reason']=reason;event('reply_discarded',sequence=packet['sequence'],reason=reason);continue
                    decision=packet['decision'];actions=packet['actions'];latest_selected=packet['sequence']
                    packet['row']['selected_s']=now();memory=decision['memory']
                    if decision['done'] and not actions:stop_reason='model_claimed_done';break
                    start_pose=np.array(observation['robot']['commanded_tcp_pose_m_rad'])
                    expected=start_pose+sum((np.r_[a['delta_xyz_m'],a['delta_yaw_rad']] for a in actions),start=np.zeros(4))
                    revision+=1
                    active={'revision':revision,'sequence':packet['sequence'],'started_s':now(),'index':0,
                        'start_at_s':decision.get('start_at_s'),
                        'result_id_at_start':(observation['fixture']['result'] or {}).get('test_id'),
                        'expected_end_pose_m_rad':expected.tolist(),'actions':actions,'segments':decision['segments'],
                        'capture_s':packet['capture_s'],'source_age_at_start_s':now()-packet['capture_s'],
                        'log':(out/f'chunk-{revision:03d}-actions.jsonl').open('w'),
                        'execution':{'requested_commands':len(actions),'accepted_commands':0,'commands':[]}}
                    event('chunk_started',revision=revision,sequence=packet['sequence'])
                    print(json.dumps({'sim_s':round(now()-t0,2),'selected':packet['sequence'],'revision':revision,
                        'summary':decision['summary'],'age_s':round(active['source_age_at_start_s'],3),'commands':len(actions)},ensure_ascii=False),flush=True)
                    break
                if stop_reason=='model_claimed_done':break
            diag=env.diagnostics()
            if len(diag['sorted'])==BOARD_COUNT:stop_reason='environment_terminal';break
            if diag['dropped']:stop_reason='board_dropped';break
            if diag.get('loop',{}).get('deadline_missed') and not continue_after_deadline:stop_reason='task_deadline_missed';break
            busy={p['worker'] for p in pending}
            if schedule=='stagger':
                waiting=[p for p in pending if p['parent_revision']==revision]
                held_for_result=awaiting_result(active,env.observe()['fixture']) if active else False
                due=not held_for_result and now()>=next_request and request_due(now=now(),
                    active_end=max(active['started_s'],active.get('start_at_s') or 0.)+len(active['actions'])*CONTROL_DT if active else None,
                    outstanding=len(waiting)+sum(p['parent_revision']==revision for p in candidates),
                    oldest_pending_age=max((now()-p['capture_s'] for p in waiting),default=0.),
                    concurrency=concurrency,default_latency=expected_latency,
                    latency_samples=[c['completed_s']-c['capture_s'] for c in calls if 'model_wall_seconds' in c])
            else:due=now()>=next_request
            if len(calls)<max_calls and due and len(busy)<concurrency:
                worker=next(i for i in range(concurrency) if i not in busy)
                obs,use=capture(env,camera_mode,width,height);capture_s=obs['capture_time_s']
                sequence=len(calls);directory=out/f'call-{sequence:03d}';directory.mkdir()
                expected=(active['expected_end_pose_m_rad'] if active else obs['robot']['commanded_tcp_pose_m_rad'])
                context={'parent_revision':revision,'committed_chunk':{'sequence':active['sequence'],'segments':active['segments'],
                             'start_at_s':active.get('start_at_s')} if active else None,
                         'expected_start_pose_m_rad':expected}
                if output_mode=='lean7':
                    context['command_period_s']=CONTROL_DT
                    context['reply_latency_s']=latency_summary([c['completed_s']-c['capture_s'] for c in calls if 'model_wall_seconds' in c])
                prompt=pipeline_prompt(obs,sequence,memory,previous,ttl,use,context,output_mode=output_mode,
                    continue_after_deadline=continue_after_deadline,
                    calibration='\n'.join(c for c in (calibration,wrist_calibration if 'wrist' in use else None) if c))
                images=[encode_png(pixels) for pixels in obs['images'].values()]
                delay=float(rng.choice(samples))*latency_scale
                write(directory/'observation.json',{k:v for k,v in obs.items() if k!='images'})
                write(directory/'pipeline-context.json',context)
                row={'sequence':sequence,'worker':worker,'cameras':list(use),'capture_s':capture_s,'sampled_delay_s':delay,'ready_s':capture_s+delay,
                     'parent_revision':revision,'issued_while_executing':active is not None}
                calls.append(row)
                pending.append({'sequence':sequence,'worker':worker,'parent_revision':revision,'requires_parent_success':active is not None,
                    'capture_wall':capture_s,'capture_s':capture_s,'capture_time_s':capture_s,'ready_s':capture_s+delay,
                    'expected_start_pose_m_rad':expected,'row':row,
                    'future':pool.submit(infer_timed,clients[worker],prompt,images,directory/'model')})
                event('request_issued',sequence=sequence,worker=worker,parent_revision=revision,overlaps_execution=active is not None)
                next_request=now()+request_interval
            if len(calls)>=max_calls and not pending and not candidates and active is None:stop_reason='max_calls';break
            if active and now()+1e-9>=(active.get('start_at_s') or 0.):
                action=active['actions'][active['index']]
                try:receipt=env.command(action,observed_at_s=active['capture_s'],ttl_s=ttl)
                except ValueError as exc:receipt={'accepted':False,'reason':'invalid_target','detail':str(exc)}
                command={'index':active['index'],'action':action,'receipt':receipt,'source_age_s':now()-active['capture_s'],'applied_at_sim_s':now()}
                active['execution']['commands'].append(command);active['log'].write(json.dumps(command)+'\n')
                if receipt['accepted']:active['execution']['accepted_commands']+=1;active['index']+=1
                else:active['index']=len(active['actions'])
            env.advance(CONTROL_DT);recorder.sample()
    except KeyboardInterrupt:stop_reason='interrupted'
    except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)};stop_reason='runner_error'
    finally:
        if active:finish_chunk()
        for client in clients:client.close()
        if pool:pool.shutdown(wait=True,cancel_futures=True)
        for packet in pending:packet['row']['discard_reason']='in_flight_at_stop'
        for packet in candidates:packet['row']['discard_reason']='unused_at_stop'
        recorder.sample(force=True);save_states(recorder)
        for camera in ('overview','top','racks_closeup'):
            obs=env.observe(cameras=(camera,),width=1440,height=960)
            Image.fromarray(obs['images'][camera]).save(out/f'final-{camera}.png')
        diag=env.diagnostics();sim_elapsed=now()-t0
        completed=[c for c in calls if 'model_wall_seconds' in c]
        execution_time=sum(len(c['execution']['commands'])*CONTROL_DT for c in chunks)
        metrics={'model_requests':len(calls),'model_replies':len(completed),'selected_chunks':len(chunks),
            'sim_elapsed_s':sim_elapsed,'wall_elapsed_s':time.monotonic()-wall_started,'virtual_pause_wall_s':paused_wall,
            'sampled_delay_s':stats([c['sampled_delay_s'] for c in calls]),
            'actual_request_latency_s':stats([c['model_wall_seconds'] for c in completed]),
            'output_tokens':stats([c['token_usage']['last']['outputTokens'] for c in completed if c.get('token_usage')]),
            'reasoning_tokens':stats([c['token_usage']['last']['reasoningOutputTokens'] for c in completed if c.get('token_usage')]),
            'source_age_at_action_start_s':stats([c['source_age_at_start_s'] for c in chunks]),
            'wait_between_chunks_s':stats([max(0.,b['started_s']-a['finished_s']) for a,b in zip(chunks,chunks[1:])]),
            'robot_motion_fraction':execution_time/sim_elapsed if sim_elapsed>0 else None,
            'discard_reasons':{r:sum(c.get('discard_reason')==r for c in calls) for r in sorted({c['discard_reason'] for c in calls if 'discard_reason' in c})},
            'boards_picked':len({e['board'] for e in diag['events'] if e['kind']=='vacuum_attached'}),
            'boards_tested':len(diag['test_receipts']),'boards_sorted_correctly':sum(r['correct'] for r in diag['sorted'].values())}
        report={'kind':'subscription_simulation_virtual_clock','evidence':config['evidence'],'config':config,'metrics':metrics,
            'stop_reason':stop_reason,'error':error,'calls':calls,'chunks':chunks,'scheduler_events':events,
            'diagnostics':diag,'direct_api_calls':0}
        save_report(out,report);env.close()
    print(json.dumps({'output':str(out),'metrics':metrics,'stop_reason':stop_reason,'error':error},indent=2),flush=True)
    if error:raise RuntimeError(str(error))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['simulate'])
    p.add_argument('--output',type=Path,default=ROOT/'runs'/f'pcba-sim-{time.strftime("%Y%m%dT%H%M%S")}')
    p.add_argument('--provider',choices=['subscription'],default='subscription',help='Decision source (default: subscription)')
    p.add_argument('--profile',type=Path,required=True,help='retained run directory or {"samples_s": [...]} JSON')
    p.add_argument('--latency-scale',type=float,default=1.,help='explicit sensitivity multiplier; label results accordingly')
    p.add_argument('--latency-seed',type=int,default=0)
    p.add_argument('--concurrency',type=int,choices=[1,2,4],default=1);p.add_argument('--duration',type=positive_float,default=150.,help='Game duration in seconds')
    p.add_argument('--max-calls',type=int,default=24);p.add_argument('--wall-seconds',type=positive_float,default=1800.,help='Wall-clock limit in seconds')
    p.add_argument('--ttl',type=float,default=12.);p.add_argument('--request-interval',type=float,default=.75)
    p.add_argument('--seed',type=int,default=0);p.add_argument('--layout',choices=['stopped','loop'],default='loop')
    p.add_argument('--camera-mode',choices=CAMERA_MODES,default='top')
    p.add_argument('--service-tier',choices=['default','priority'],default='default',
        help='default: cheaper development inference; delays still come from the profile')
    p.add_argument('--effort',choices=['low','medium','high','xhigh','max','ultra'],default='low',
        help='reasoning effort of the decision model; delays still come from --profile')
    p.add_argument('--no-transport-tuning',action='store_true')
    p.add_argument('--continue-after-deadline',action='store_true')
    add_latency_arguments(p,transport_flag=False)
    p.set_defaults(output_mode='lean',schedule='stagger')
    a=p.parse_args()
    with recording(a.output,game='pcba',command='simulate',provider=a.provider,clock='virtual',detail_file='report.json'):
        simulate_pipeline(a.output,profile=a.profile,latency_scale=a.latency_scale,latency_seed=a.latency_seed,
            concurrency=a.concurrency,sim_duration=a.duration,max_calls=a.max_calls,max_wall=a.wall_seconds,ttl=a.ttl,
            request_interval=a.request_interval,seed=a.seed,layout=a.layout,camera_mode=a.camera_mode,
            image_size=parse_image_size(a.image_size),output_mode=a.output_mode,schedule=a.schedule,
            expected_latency=a.expected_latency,transport_tuning=not a.no_transport_tuning,service_tier=a.service_tier,
            continue_after_deadline=a.continue_after_deadline,top_calibration=a.top_calibration,effort=a.effort)
