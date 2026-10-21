"""Serialized robot execution with overlapping, versioned visual inference."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import argparse
import json
import threading
import time
import numpy as np
from PIL import Image
from .environment import PCBATestCell, RealtimeSession
from .scene import BOARD_COUNT
from .runner import ROOT, POLICY, Recorder, freeze, write, parse_decision, policy_prompt, execute_chunk
from .latency import stats

GUARD_KEYS={'vacuum_ok','fixture_board_present','clamp_state','tester_state','result_test_id'}


def parse_pipeline(answer):
    value=json.loads(answer);base={'summary','memory','done','segments','start_guard'}
    if not isinstance(value,dict) or set(value) not in (base,base|{'start_at_s'}):
        raise ValueError('Unexpected pipeline output fields')
    start_at=value.pop('start_at_s',None)
    if start_at is not None and (type(start_at) not in (int,float) or not np.isfinite(start_at)):raise ValueError('Invalid start_at_s')
    guard=value.pop('start_guard')
    if not isinstance(guard,dict) or set(guard)!=GUARD_KEYS:raise ValueError('Invalid guard fields')
    for key in ('vacuum_ok','fixture_board_present'):
        if guard[key] is not None and type(guard[key]) is not bool:raise ValueError('Invalid boolean guard')
    if guard['clamp_state'] not in (None,'open','closed','opening','closing'):raise ValueError('Invalid clamp guard')
    if guard['tester_state'] not in (None,'idle','running','complete'):raise ValueError('Invalid tester guard')
    if guard['result_test_id'] is not None and not isinstance(guard['result_test_id'],str):raise ValueError('Invalid test ID guard')
    d,actions=parse_decision(json.dumps(value));d['start_guard']=guard;d['start_at_s']=start_at
    return d,actions


def rejection(packet,*,revision,parent_success,latest_selected,observation,wall_now,ttl):
    """A transport gate only: no target choice, object truth or automatic task logic."""
    if packet['sequence']<=latest_selected:return 'superseded_sequence'
    if packet['parent_revision']!=revision:return 'superseded_parent'
    if packet['requires_parent_success'] and not parent_success:return 'parent_failed'
    if wall_now-packet['capture_wall']>ttl or observation['capture_time_s']-packet['capture_time_s']>ttl:return 'expired_source'
    if not np.allclose(observation['robot']['commanded_tcp_pose_m_rad'],packet['expected_start_pose_m_rad'],atol=1e-5,rtol=0):return 'incompatible_robot_start'
    # Model-authored start time: forwarded literally, never moved earlier or later.
    start_at=packet['decision'].get('start_at_s')
    if start_at is not None:
        if start_at<observation['capture_time_s']-1e-6:return 'late_start'
        if start_at-packet['capture_time_s']>ttl-.5:return 'start_beyond_ttl'
    f=observation['fixture'];g=packet['decision']['start_guard']
    actual={'vacuum_ok':observation['robot']['vacuum_ok'],'fixture_board_present':f['board_present'],
            'clamp_state':f['clamp_state'],'tester_state':f['tester_state'],
            'result_test_id':(f['result'] or {}).get('test_id')}
    if any(value is not None and actual[key]!=value for key,value in g.items()):return 'start_guard_mismatch'
    return None


CONTROL_DT=.05
OUTPUT_MODES=('full','lean','lean2','lean3','lean4','lean5','lean6','lean7')
CAMERA_MODES=('multi','top','adaptive')
FIXTURE_XY=np.array([0.,-.08])
PICK_LANE_X=-.36
SCHEDULES=('interval','stagger')


def latency_quantile(samples,q,default):
    """Public historical reply latency (capture to reply); never a future draw."""
    recent=list(samples)[-12:]
    return float(np.quantile(recent,q)) if len(recent)>=3 else float(default)


def hedge_quantiles(concurrency):
    # Earlier requests use a pessimistic latency so a reply is ready; later ones are fresher.
    return {1:(.5,),2:(.8,.4),4:(.9,.7,.5,.3)}[concurrency]


def request_due(*,now,active_end,outstanding,oldest_pending_age,concurrency,latency_samples,default_latency):
    """Transport timing only: decides WHEN to capture, never what the robot does."""
    if outstanding>=concurrency:return False
    if active_end is None:
        # Idle robot: ask now; hedge with another request only if the first is unusually slow.
        return outstanding==0 or oldest_pending_age>=latency_quantile(latency_samples,.8,default_latency)
    # Executing: capture about one reply latency before the committed chunk ends.
    q=hedge_quantiles(concurrency)[outstanding]
    return now>=active_end-latency_quantile(latency_samples,q,default_latency)


def awaiting_result(active,fixture):
    """Transport timing only: a chunk that starts a test should not be followed by a capture
    taken before that test's result is public, or the next reply cannot choose an output."""
    if not active or not any(a.get('fixture')=='start_test' for a in active['actions']):return False
    return ((fixture.get('result') or {}).get('test_id'))==active.get('result_id_at_start')


def encode_png(pixels):
    # Fast lossless compression: identical pixels, less CPU on the capture path.
    buffer=BytesIO();Image.fromarray(pixels).save(buffer,format='PNG',compress_level=1);return buffer.getvalue()


def top_calibration_text(model,width,height,z=.8008):
    """Public fixed overhead-camera geometry (the camera never moves); no object state."""
    import mujoco
    data=mujoco.MjData(model);mujoco.mj_forward(model,data);cid=model.camera('top').id
    pos=data.cam_xpos[cid];rot=data.cam_xmat[cid].reshape(3,3)
    if not np.allclose(rot,np.eye(3),atol=1e-6):raise ValueError('Top camera is not axis-aligned overhead')
    scale=np.tan(np.deg2rad(model.cam_fovy[cid])/2)*2*(pos[2]-z)/height  # metres per pixel at height z
    x0=pos[0]-scale*width/2;y0=pos[1]+scale*height/2;speed=.055/scale
    return (f'PUBLIC TOP-CAMERA CALIBRATION ({width}x{height} overhead image, straight down, exact at board height z={z}): '
            f'world_x = {scale:.6f}*u {x0:+.4f}; world_y = {y0:.4f} - {scale:.6f}*v (u right, v down; 1 px = {scale*1000:.2f} mm). '
            f'Right-straight lane x=-0.36 is u={(-.36-x0)/scale:.0f}; pick zone y=+0.14..-0.14 is v={(y0-.14)/scale:.0f}..{(y0+.14)/scale:.0f}. '
            f'Belt speed 0.055 m/s = {speed:.1f} px/s; on the right straight boards move toward smaller v.')


def wrist_calibration_text(model,width,height):
    """Public fixed wrist-camera geometry relative to the TCP (moves with the tool); no object state."""
    import mujoco
    data=mujoco.MjData(model);mujoco.mj_forward(model,data)
    cid=model.camera('wrist').id;tool=model.body('tool').id;tcp=model.site('tcp').id
    R=data.xmat[tool].reshape(3,3);rel=R.T@(data.cam_xpos[cid]-data.site_xpos[tcp])
    if not np.allclose(data.cam_xmat[cid].reshape(3,3),R,atol=1e-6):raise ValueError('Wrist camera is not aligned with the tool')
    f=(height/2)/np.tan(np.deg2rad(model.cam_fovy[cid])/2);depth=rel[2];scale=depth/f
    u0=width/2-f*rel[0]/depth;v0=height/2+f*rel[1]/depth  # TCP pixel at TCP height
    edge=height/2-f*(-rel[1]-.0375)/depth
    v_wait=height/2-f*(-rel[1])/(depth+.0032)  # cup pixel in the board plane while waiting 3.2 mm above it
    return (f'PUBLIC WRIST-CAMERA CALIBRATION ({width}x{height}, fixed to the tool, looking straight down; image axes follow the tool: '
            f'+u = tool +x, image up = tool +y). The TCP projects to u={u0:.0f}, v={v0:.0f} (just outside the top edge). '
            f'At the held-board plane (TCP height) 1 px = {scale*1000:.3f} mm; a plane 10 mm lower is {(depth+.01)/f*1000:.3f} mm/px. '
            f'A board held exactly centred and square on the TCP shows its near (tool -y) edge as a horizontal line at v={edge:.0f} '
            f'spanning u={width/2-f*.055/depth:.0f}..{width/2+f*.055/depth:.0f}. Board centre offset from TCP in tool axes: '
            f'first yaw_rel = -atan(edge slope dv/du) (board yaw relative to tool), then '
            f'dx = (edge-midpoint u - {width/2:.0f}) * {scale*1000:.3f} - 37.5*sin(yaw_rel) mm, dy = ({edge:.0f} - edge-midpoint v) * {scale*1000:.3f} - 37.5*(1-cos(yaw_rel)) mm. '
            f'Waiting {(.0032)*1000:.1f} mm above a board centre plane with tool yaw 0 on the right straight, the cup sits at u={width/2:.0f}, v={v_wait:.0f} '
            f'in that plane and boards approach from the image bottom: a board centre at (u, v) is (u - {width/2:.0f}) * {(depth+.0032)/f*1000:.3f} mm to the side of the cup '
            f'(+ = world +x) and (v {"+" if v_wait<0 else "-"} {abs(v_wait):.0f}) * {(depth+.0032)/f*1000:.3f} mm upstream; at 55 mm/s it arrives after that distance / 55 seconds.')


def select_cameras(camera_mode,obs):
    """Which public views to send; 'adaptive' adds the wrist view only from public signals."""
    if camera_mode=='multi':return ('overview','top','wrist')
    if camera_mode=='top':return ('top',)
    tcp=np.asarray(obs['robot']['tcp_position_m'])
    near_fixture=np.linalg.norm(tcp[:2]-FIXTURE_XY)<.08
    waiting_in_pick_zone=abs(tcp[0]-PICK_LANE_X)<.10 and abs(tcp[1])<.25 and tcp[2]<.86
    return ('top','wrist') if obs['robot']['vacuum_ok'] or near_fixture or waiting_in_pick_zone else ('top',)


def render_cameras(camera_mode):
    return {'multi':('overview','top','wrist'),'top':('top',),'adaptive':('top','wrist')}[camera_mode]


def capture(env,camera_mode,width,height):
    """One snapshot for all candidate views, then keep only the selected ones."""
    obs=env.observe(cameras=render_cameras(camera_mode),width=width,height=height)
    use=select_cameras(camera_mode,obs);obs['images']={k:obs['images'][k] for k in use}
    return obs,use


def pipeline_prompt(obs,sequence,memory,previous,ttl,cameras,context,*,output_mode='full',continue_after_deadline=False,calibration=None):
    prompt=policy_prompt(obs,sequence,memory,previous,ttl,camera_names=cameras)+'\n'+(POLICY/'pipeline.txt').read_text()
    level=OUTPUT_MODES.index(output_mode)  # each lean level adds to the previous one
    for minimum,name in ((1,'pipeline-lean.txt'),(2,'pipeline-lean2.txt'),(3,'pipeline-place.txt'),(4,'pipeline-intercept.txt')):
        if level>=minimum:prompt+=('\n' if minimum==1 else '')+(POLICY/name).read_text()
    # lean5 and lean6 are alternative throughput cycles (four vs two replies per board);
    # lean7 is lean5 plus model-timed chunk starts for predictive interception.
    if output_mode in ('lean5','lean6','lean7'):prompt+=(POLICY/('pipeline-cycle2.txt' if output_mode=='lean6' else 'pipeline-cycle.txt')).read_text()
    if output_mode=='lean7':prompt+=(POLICY/'pipeline-timed.txt').read_text()
    if calibration:prompt+=calibration+'\n'
    prompt+='\nTRUSTED PIPELINE CONTEXT:\n'+json.dumps(context)
    if continue_after_deadline:
        prompt+='\nDIAGNOSTIC CONTINUATION: If a lap/batch deadline has passed, still attempt all remaining boards. Deadline failure remains latched. Do not claim done merely because a deadline passed.\n'
    return prompt


def pipeline_schema(output_mode):
    name='pipeline.schema.json' if output_mode=='full' else 'pipeline-timed.schema.json' if output_mode=='lean7' else 'pipeline-lean.schema.json'
    return json.loads((POLICY/name).read_text())


def parse_image_size(value):
    width,height=(int(v) for v in str(value).lower().split('x'))
    if not (160<=width<=1280 and 120<=height<=960):raise ValueError('image size must be within 160x120..1280x960')
    return width,height


def infer_timed(client,prompt,images,directory):
    started=time.monotonic();answer,meta=client.act(prompt,images,directory)
    meta={**meta,'transport_started_wall':started,'transport_finished_wall':time.monotonic()}
    return answer,meta


def latency_summary(samples):
    """Public historical reply latency (capture to reply) for the actor's own planning."""
    recent=list(samples)[-20:]
    if len(recent)<3:return None
    return {'n':len(recent),'p50_s':round(float(np.quantile(recent,.5)),2),'p90_s':round(float(np.quantile(recent,.9)),2)}


def execute_timed(*args,start_at=None,**kwargs):
    env=args[0];stop=kwargs['stop']
    while start_at is not None and not stop.is_set() and env.observe()['capture_time_s']<start_at:stop.wait(.005)
    started=time.monotonic();execution=execute_chunk(*args,**kwargs)
    return {**execution,'execution_started_wall':started,'execution_finished_wall':time.monotonic()}


def save_states(recorder):
    # No online replay rendering: state samples remain available for native export.
    write(recorder.out/'replay.json',{'frames':recorder.frames,'kind':'native state snapshots; no interpolation'})
    if recorder.states:
        np.savez_compressed(recorder.out/'recorded-states.npz',**{
            k:np.stack([state[k] for state in recorder.states]) for k in recorder.states[0]})


def evaluate_pipeline(output,*,concurrency=1,duration=120.,max_calls=24,ttl=12.,request_interval=.75,seed=0,layout='stopped',physics_process=False,continue_after_deadline=False,camera_mode='multi',
                      image_size=(640,480),output_mode='full',schedule='interval',expected_latency=8.,transport_tuning=False,top_calibration=False):
    from runtime.subscription import SubscriptionClient
    if concurrency not in (1,2,4):raise ValueError('concurrency must be 1, 2 or 4')
    if layout not in ('stopped','loop'):raise ValueError('Unknown conveyor layout')
    if camera_mode not in CAMERA_MODES:raise ValueError('Unknown camera mode')
    cameras=render_cameras(camera_mode)
    if output_mode not in OUTPUT_MODES or schedule not in SCHEDULES:raise ValueError('Unknown output mode or schedule')
    width,height=parse_image_size('x'.join(map(str,image_size)))
    if not 0<duration<=600 or not 1<=max_calls<=400 or not 0<ttl<=15 or request_interval<.25:
        raise ValueError('Invalid pipeline limits')
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    config={'concurrency':concurrency,'duration_s':duration,'max_calls':max_calls,'observation_ttl_s':ttl,
            'request_interval_s':request_interval,'seed':seed,'model':'gpt-6.1-sol','service_tier':'priority',
            'layout':layout,'physics_process':physics_process,'continue_after_deadline':continue_after_deadline,
            'policy_cameras':list(cameras),'image_size':[width,height],'png_compress_level':1,
            'output_mode':output_mode,'schedule':schedule,'expected_latency_s':expected_latency,'top_calibration':top_calibration,
            'transport':{'quota_check_every_calls':10 if transport_tuning else 1,'prestarted_threads':transport_tuning},
            'execution_lanes':1,'pipeline':'infer next chunk during current literal execution; guarded predicted command endpoint'}
    if layout=='loop':
        from .loop import PCBALoopCell
        cell_type=PCBALoopCell
    else:cell_type=PCBATestCell
    freeze(out,config)
    if physics_process:
        from .process_clock import ProcessCell,ProcessSession
        env=ProcessCell(layout=layout,seed=seed,asset_dir=out/'assets');session_type=ProcessSession
    else:env=cell_type(seed=seed,asset_dir=out/'assets');session_type=RealtimeSession
    (out/'scene.xml').write_text(env.xml)
    calibration=top_calibration_text(env.model,width,height) if top_calibration and 'top' in cameras else None
    wrist_calibration=wrist_calibration_text(env.model,width,height) if camera_mode=='adaptive' else None
    clients=[];pending={};candidates=[];calls=[];chunks=[];events=[];memory='';previous=None
    revision=0;parent_success=True;latest_selected=-1;active=None;error=None;stop_reason='wall_duration'
    stop=threading.Event();pool=None;control=None;session=None;recorder=Recorder(env,out);timing=None;initial_sim_s=None
    def event(kind,**fields):events.append({'wall':time.monotonic(),'sim_s':env.observe()['capture_time_s'],'kind':kind,**fields})
    try:
        env.observe(cameras=cameras,width=width,height=height)
        for i in range(concurrency):
            clients.append(SubscriptionClient(output=out/f'worker-{i}',output_schema=pipeline_schema(output_mode),
                system=(POLICY/'system.txt').read_text(),auth_only_home=True,record_reasoning=False,service_tier='priority',
                quota_every=10 if transport_tuning else 1,prestart=transport_tuning))
        pool=ThreadPoolExecutor(max_workers=concurrency,thread_name_prefix='pcba-infer')
        control=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pcba-execute')
        initial_sim_s=env.observe()['capture_time_s']
        session=session_type(env).start();started=time.monotonic();end=started+duration;next_request=started;next_diagnostic=started
        next_result_poll=started;held_for_result=False
        recorder.sample(force=True)
        while time.monotonic()<end:
            if active and active['future'].done():
                execution=active['future'].result();active['log'].close()
                parent_success=execution['accepted_commands']==execution['requested_commands']
                finished=execution['execution_finished_wall'];row={k:v for k,v in active.items() if k not in ('future','log','actions')}
                row.update({'started_wall':execution['execution_started_wall'],'finished_wall':finished,'execution':execution});chunks.append(row)
                write(out/f"chunk-{revision:03d}.json",row);previous={k:v for k,v in execution.items() if k!='commands'}
                event('chunk_completed',revision=revision,accepted=execution['accepted_commands'],requested=execution['requested_commands'])
                active=None
            for future in list(pending):
                if not future.done():continue
                packet=pending.pop(future);row=packet['row'];row['completed_wall']=time.monotonic()
                try:
                    answer,meta=future.result();row['native_wall_seconds']=meta['wall_seconds'];row['transport_stages_s']=meta.get('stages_s');row['model_wall_seconds']=meta['transport_finished_wall']-meta['transport_started_wall'];row['token_usage']=meta['token_usage'];row['transport_started_wall']=meta['transport_started_wall'];row['transport_finished_wall']=meta['transport_finished_wall']
                    decision,actions=parse_pipeline(answer);packet.update({'decision':decision,'actions':actions})
                    row['summary']=decision['summary'];candidates.append(packet)
                    event('reply_received',sequence=packet['sequence'],parent_revision=packet['parent_revision'])
                except (ValueError,TypeError) as exc:row['discard_reason']='invalid_output';row['detail']=str(exc)
                except Exception as exc:row['discard_reason']='request_error';row['detail']=str(exc)
            # Drop obsolete branches promptly; a discarded reply never changes memory or motion.
            for packet in list(candidates):
                row=packet['row']
                if packet['parent_revision']!=revision or packet['sequence']<=latest_selected:
                    row['discard_reason']='superseded_parent_or_sequence';candidates.remove(packet)
            if active is None and candidates:
                observation=env.observe()
                for packet in sorted(candidates,key=lambda p:p['sequence'],reverse=True):
                    reason=rejection(packet,revision=revision,parent_success=parent_success,latest_selected=latest_selected,
                        observation=observation,wall_now=time.monotonic(),ttl=ttl)
                    candidates.remove(packet)
                    if reason:
                        packet['row']['discard_reason']=reason;event('reply_discarded',sequence=packet['sequence'],reason=reason);continue
                    decision=packet['decision'];actions=packet['actions'];latest_selected=packet['sequence']
                    packet['row']['selected_wall']=time.monotonic();memory=decision['memory']
                    if decision['done'] and not actions:stop_reason='model_claimed_done';stop.set();break
                    start_pose=np.array(observation['robot']['commanded_tcp_pose_m_rad'])
                    expected=start_pose+sum((np.r_[a['delta_xyz_m'],a['delta_yaw_rad']] for a in actions),start=np.zeros(4))
                    revision+=1;log=(out/f'chunk-{revision:03d}-actions.jsonl').open('w')
                    now=time.monotonic();active={'revision':revision,'sequence':packet['sequence'],'started_wall':now,'start_at_s':decision.get('start_at_s'),
                        'result_id_at_start':(observation['fixture']['result'] or {}).get('test_id'),
                        'expected_end_pose_m_rad':expected.tolist(),'actions':actions,'segments':decision['segments'],'log':log,
                        'source_age_at_start_s':now-packet['capture_wall'],
                        'start_delay_s':max(0.,(decision.get('start_at_s') or 0.)-observation['capture_time_s']),
                        'future':control.submit(execute_timed,env,actions,capture_time=packet['capture_time_s'],
                            capture_wall=packet['capture_wall'],ttl=ttl,stop=stop,log=log,start_at=decision.get('start_at_s'))}
                    event('chunk_started',revision=revision,sequence=packet['sequence'])
                    print(json.dumps({'selected':packet['sequence'],'revision':revision,'summary':decision['summary'],
                        'age_s':round(active['source_age_at_start_s'],3),'commands':len(actions)},ensure_ascii=False),flush=True)
                    break
            if stop.is_set():break
            if time.monotonic()>=next_diagnostic:
                diag=env.diagnostics();next_diagnostic=time.monotonic()+.25
                if len(diag['sorted'])==BOARD_COUNT:stop_reason='environment_terminal';break
                if diag['dropped']:stop_reason='board_dropped';break
                if diag.get('loop',{}).get('deadline_missed') and not continue_after_deadline:stop_reason='task_deadline_missed';break
            busy={packet['worker'] for packet in pending.values()}
            now=time.monotonic()
            if schedule=='stagger':
                waiting=[p for p in pending.values() if p['parent_revision']==revision]
                if not active or not any(a.get('fixture')=='start_test' for a in active['actions']):held_for_result=False
                elif now>=next_result_poll:held_for_result=awaiting_result(active,env.observe()['fixture']);next_result_poll=now+.1
                due=not held_for_result and now>=next_request and request_due(now=now,
                    active_end=active['started_wall']+active['start_delay_s']+len(active['actions'])*CONTROL_DT if active else None,
                    outstanding=len(waiting)+sum(p['parent_revision']==revision for p in candidates),
                    oldest_pending_age=max((now-p['row']['issued_wall'] for p in waiting),default=0.),
                    concurrency=concurrency,default_latency=expected_latency,
                    latency_samples=[c['completed_wall']-c['capture_wall'] for c in calls if 'model_wall_seconds' in c])
            else:due=now>=next_request
            if len(calls)<max_calls and due and len(busy)<concurrency:
                worker=next(i for i in range(concurrency) if i not in busy)
                capture_wall=time.monotonic();obs,use=capture(env,camera_mode,width,height)
                sequence=len(calls);directory=out/f'call-{sequence:03d}';directory.mkdir()
                expected=(active['expected_end_pose_m_rad'] if active else obs['robot']['commanded_tcp_pose_m_rad'])
                context={'parent_revision':revision,'committed_chunk':{'sequence':active['sequence'],'segments':active['segments'],
                             'start_at_s':active.get('start_at_s')} if active else None,
                         'expected_start_pose_m_rad':expected}
                if output_mode=='lean7':
                    context['command_period_s']=CONTROL_DT
                    context['reply_latency_s']=latency_summary([c['completed_wall']-c['capture_wall'] for c in calls if 'model_wall_seconds' in c])
                prompt=pipeline_prompt(obs,sequence,memory,previous,ttl,use,context,output_mode=output_mode,
                    continue_after_deadline=continue_after_deadline,
                    calibration='\n'.join(c for c in (calibration,wrist_calibration if 'wrist' in use else None) if c))
                images=[encode_png(pixels) for pixels in obs['images'].values()]
                write(directory/'observation.json',{k:v for k,v in obs.items() if k!='images'})
                write(directory/'pipeline-context.json',context)
                row={'sequence':sequence,'worker':worker,'cameras':list(use),'issued_wall':time.monotonic(),'capture_wall':capture_wall,
                     'capture_time_s':obs['capture_time_s'],'parent_revision':revision,'issued_while_executing':active is not None and not active['future'].done()}
                calls.append(row)
                packet={'sequence':sequence,'worker':worker,'parent_revision':revision,'requires_parent_success':active is not None,
                    'capture_wall':capture_wall,'capture_time_s':obs['capture_time_s'],'expected_start_pose_m_rad':expected,'row':row}
                pending[pool.submit(infer_timed,clients[worker],prompt,images,directory/'model')]=packet
                event('request_issued',sequence=sequence,worker=worker,parent_revision=revision,overlaps_execution=active is not None)
                next_request=time.monotonic()+request_interval
            if len(calls)>=max_calls and not pending and not candidates and active is None:stop_reason='max_calls';break
            recorder.sample();time.sleep(.01)
    except KeyboardInterrupt:stop_reason='interrupted'
    except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)};stop_reason='runner_error'
    finally:
        stop.set()
        if active:
            execution=active['future'].result(timeout=5.);active['log'].close()
            row={k:v for k,v in active.items() if k not in ('future','log','actions')}
            row.update({'started_wall':execution['execution_started_wall'],'finished_wall':execution['execution_finished_wall'],'execution':execution});chunks.append(row)
        if session:session.close();timing=session.timing()
        for client in clients:client.close()
        if pool:pool.shutdown(wait=True,cancel_futures=True)
        if control:control.shutdown(wait=True,cancel_futures=True)
        for packet in pending.values():packet['row']['discard_reason']='in_flight_at_stop'
        for packet in candidates:packet['row']['discard_reason']='unused_at_stop'
        recorder.sample(force=True);save_states(recorder)
        for camera in ('overview','top','racks_closeup'):
            obs=env.observe(cameras=(camera,),width=1440,height=960)
            Image.fromarray(obs['images'][camera]).save(out/f'final-{camera}.png')
        diag=env.diagnostics()
        if timing:
            timing['wall_minus_sim_s']=timing['wall_elapsed_s']-timing['sim_elapsed_s']
            timing['timing_valid']=timing['max_tick_lag_s']<=.02 and abs(timing['wall_minus_sim_s'])<=max(.05,timing['wall_elapsed_s']*.01)
        completed=[c for c in calls if 'model_wall_seconds' in c];selected=[c for c in calls if 'selected_wall' in c]
        intervals=[b['selected_wall']-a['selected_wall'] for a,b in zip(selected,selected[1:])]
        execution_time=sum(c['finished_wall']-c['started_wall'] for c in chunks)
        overlap_seconds=sum(max(0.,min(c['transport_finished_wall'],chunk['finished_wall'])-max(c['transport_started_wall'],chunk['started_wall']))
            for c in completed for chunk in chunks)
        transitions=[max(0.,b['started_wall']-a['finished_wall']) for a,b in zip(chunks,chunks[1:])]
        commands=[c for chunk in chunks for c in chunk['execution']['commands']]
        metrics={'model_requests':len(calls),'model_replies':len(completed),'selected_chunks':len(selected),
            'inference_execution_overlap_s':overlap_seconds,
            'requests_started_during_execution':sum(c['issued_while_executing'] for c in calls),
            'discarded_replies':sum('discard_reason' in c for c in calls if 'model_wall_seconds' in c),
            'requests_in_flight_at_stop':sum(c.get('discard_reason')=='in_flight_at_stop' for c in calls),
            'request_latency_s':stats([c['model_wall_seconds'] for c in completed]),
            'capture_to_reply_s':stats([c['completed_wall']-c['capture_wall'] for c in completed]),
            'output_tokens':stats([c['token_usage']['last']['outputTokens'] for c in completed if c.get('token_usage')]),
            'reasoning_tokens':stats([c['token_usage']['last']['reasoningOutputTokens'] for c in completed if c.get('token_usage')]),
            'robot_motion_fraction':execution_time/timing['wall_elapsed_s'] if timing and timing.get('wall_elapsed_s') else None,
            'discard_reasons':{r:sum(c.get('discard_reason')==r for c in calls) for r in sorted({c['discard_reason'] for c in calls if 'discard_reason' in c})},'usable_chunk_start_interval_s':stats(intervals),
            'source_age_at_action_start_s':stats([c['source_age_at_start_s'] for c in chunks]),
            'wait_between_chunks_s':stats(transitions),'execution_wall_s':execution_time,
            'accepted_commands':sum(c['receipt']['accepted'] for c in commands),
            'rejected_commands':sum(not c['receipt']['accepted'] for c in commands),
            'boards_picked':len({e['board'] for e in diag['events'] if e['kind']=='vacuum_attached'}),
            'boards_tested':len(diag['test_receipts']),'boards_sorted_correctly':sum(r['correct'] for r in diag['sorted'].values()),
            'five_board_completion_sim_s':(max(e['time_s'] for e in diag['events'] if e['kind']=='board_sorted')-initial_sim_s)
                if initial_sim_s is not None and len(diag['sorted'])==BOARD_COUNT and all(r['correct'] for r in diag['sorted'].values()) else None,
            'five_board_completion_detected_wall_s':timing['wall_elapsed_s'] if timing and stop_reason=='environment_terminal' and all(r['correct'] for r in diag['sorted'].values()) else None}
        report={'kind':'actual_subscription_async_pipeline','config':config,'metrics':metrics,'timing':timing,
            'stop_reason':stop_reason,'error':error,'calls':calls,'chunks':chunks,'scheduler_events':events,
            'diagnostics':diag,'direct_api_calls':0,'video':'native state snapshots saved for export; no online rendering beyond policy views'}
        write(out/'report.json',report);env.close()
    print(json.dumps({'output':str(out),'metrics':metrics,'timing':timing,'error':error},indent=2),flush=True)
    if error:raise RuntimeError(str(error))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['pipeline'])
    p.add_argument('--output',type=Path,default=ROOT/'runs'/f'pcba-pipeline-{time.strftime("%Y%m%dT%H%M%S")}')
    p.add_argument('--concurrency',type=int,choices=[1,2,4],default=1);p.add_argument('--duration',type=float,default=120.)
    p.add_argument('--max-calls',type=int,default=24);p.add_argument('--ttl',type=float,default=12.)
    p.add_argument('--request-interval',type=float,default=.75);p.add_argument('--seed',type=int,default=0)
    p.add_argument('--layout',choices=['stopped','loop'],default='stopped')
    p.add_argument('--physics-process',action='store_true')
    p.add_argument('--continue-after-deadline',action='store_true')
    p.add_argument('--camera-mode',choices=CAMERA_MODES,default='multi')
    add_latency_arguments(p)
    a=p.parse_args();evaluate_pipeline(a.output,concurrency=a.concurrency,duration=a.duration,max_calls=a.max_calls,
        ttl=a.ttl,request_interval=a.request_interval,seed=a.seed,layout=a.layout,
        physics_process=a.physics_process,continue_after_deadline=a.continue_after_deadline,camera_mode=a.camera_mode,
        image_size=parse_image_size(a.image_size),output_mode=a.output_mode,schedule=a.schedule,
        expected_latency=a.expected_latency,transport_tuning=a.transport_tuning,top_calibration=a.top_calibration)


def add_latency_arguments(p,transport_flag=True):
    p.add_argument('--image-size',default='640x480',help='policy camera WIDTHxHEIGHT')
    p.add_argument('--output-mode',choices=OUTPUT_MODES,default='full',help='lean: short summary/memory and compact numbers')
    p.add_argument('--schedule',choices=SCHEDULES,default='interval',
        help='stagger: capture about one reply latency before the committed chunk ends')
    p.add_argument('--top-calibration',action='store_true',help='state the fixed overhead pixel-to-world mapping in the prompt')
    p.add_argument('--expected-latency',type=float,default=8.,help='capture-to-reply seconds assumed until 3 replies are measured')
    if transport_flag:
        p.add_argument('--transport-tuning',action='store_true',help='quota check every 10 calls and prestarted native threads')
