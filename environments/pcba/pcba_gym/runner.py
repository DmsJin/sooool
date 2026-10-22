"""Continuous subscription visual-action baseline; no oracle motion controller."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import argparse
import json
import math
from pathlib import Path
import threading
import time
import numpy as np
import mujoco
from PIL import Image
from runtime.evaluation import recording
from runtime.options import positive_float
from .environment import PCBATestCell, RealtimeSession
from .scene import BOARD_COUNT

ROOT=Path(__file__).resolve().parents[3]
POLICY=ROOT/'policies/pcba'


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


def save_report(out,report):
    """Keep aggregate task/calibration results in the index and raw trajectories in the report."""
    write(out/'report.json',report)
    summary={'kind':report['kind'],'error':report['error']}
    for name in ('metrics','timing','stop_reason','direct_api_calls','model_calls_attempted',
                 'model_calls_completed','actual_model_calls_completed','physics_running','handling_score','summaries'):
        if name in report:
            summary[name]=report[name]
    write(out/'summary.json',summary)


def parse_decision(answer):
    """Validate an entire literal chunk before executing any of its actions."""
    d=json.loads(answer)
    if not isinstance(d,dict) or set(d)!={'summary','memory','done','segments'}:
        raise ValueError('Unexpected decision fields')
    if type(d['done']) is not bool or not isinstance(d['summary'],str) or not isinstance(d['memory'],str):
        raise ValueError('Malformed decision metadata')
    if len(d['summary'])>300 or len(d['memory'])>1600:raise ValueError('Decision text exceeds limit')
    if not isinstance(d['segments'],list) or len(d['segments'])>32:raise ValueError('Too many segments')
    actions=[]
    for s in d['segments']:
        if not isinstance(s,dict) or set(s)!={'delta_xyz_m','delta_yaw_rad','repeat','vacuum','fixture'}:
            raise ValueError('Unexpected segment fields')
        delta=np.asarray(s['delta_xyz_m'],float);yaw=s['delta_yaw_rad'];repeat=s['repeat']
        if delta.shape!=(3,) or not np.all(np.isfinite(delta)) or np.linalg.norm(delta)>.025:
            raise ValueError('Invalid translation')
        if type(yaw) not in (int,float) or not np.isfinite(yaw) or abs(yaw)>.2:
            raise ValueError('Invalid yaw')
        if type(repeat) is not int or not 1<=repeat<=120:raise ValueError('Invalid repeat')
        if s['vacuum'] is not None and type(s['vacuum']) is not bool:raise ValueError('Invalid vacuum')
        if s['fixture'] not in (None,'close','open','start_test'):raise ValueError('Invalid fixture')
        if s['fixture'] is not None and repeat!=1:raise ValueError('Fixture requests cannot repeat')
        action={'delta_xyz_m':delta.tolist(),'delta_yaw_rad':yaw}
        if s['vacuum'] is not None:action['vacuum']=s['vacuum']
        if s['fixture'] is not None:action['fixture']=s['fixture']
        actions.extend([action.copy() for _ in range(repeat)])
    if len(actions)>120:raise ValueError('Chunk exceeds six-second horizon')
    if not actions and not d['done']:raise ValueError('Empty nonterminal chunk')
    return d,actions


def policy_prompt(observation,sequence,memory,previous,ttl,camera_names=None):
    # Deliberate allowlist: evaluator scores/poses and future outcomes cannot enter.
    public={k:observation[k] for k in ('task','capture_time_s','robot','fixture','conveyor','outputs','last_action_receipt')}
    task_file='task-loop.txt' if observation['conveyor'].get('layout')=='recirculating_racetrack' else 'task.txt'
    task_text=(POLICY/task_file).read_text()
    if camera_names is not None:
        task_text=task_text.replace('Camera order: overview, overhead/top, wrist.',
            'Camera input order: '+', '.join(camera_names)+'. Only these views are supplied; top is the fixed overhead camera.')
    return (task_text+ '\n\nTRUSTED OBSERVATION '+str(sequence)+
            f' (valid for {ttl:g} seconds including inference and execution):\n'+
            json.dumps(public,separators=(',',':'))+'\nYOUR PREVIOUS MEMORY:\n'+memory+
            '\nPREVIOUS CHUNK EXECUTION RECEIPT:\n'+json.dumps(previous,separators=(',',':')))


def execute_chunk(env,actions,*,capture_time,capture_wall,ttl,stop,log):
    """Only validation, expiry and scheduling; never chooses/repairs a target."""
    rows=[];deadline=time.monotonic()
    for index,action in enumerate(actions):
        if stop.is_set():break
        if stop.wait(max(0.,deadline-time.monotonic())):break
        lateness=max(0.,time.monotonic()-deadline)
        age=time.monotonic()-capture_wall
        if age>ttl:
            receipt={'accepted':False,'reason':'expired_wall_observation'}
        else:
            try:receipt=env.command(action,observed_at_s=capture_time,ttl_s=ttl)
            except ValueError as exc:receipt={'accepted':False,'reason':'invalid_target','detail':str(exc)}
        row={'index':index,'action':action,'receipt':receipt,'source_age_wall_s':age,
             'applied_at_sim_s':env.observe()['capture_time_s'],'scheduling_lateness_s':lateness}
        rows.append(row);log.write(json.dumps(row)+'\n');log.flush()
        if not receipt['accepted']:break
        # Late commands never execute a burst to hide their lateness.
        deadline=max(deadline+.05,time.monotonic())
    stop.wait(max(0.,deadline-time.monotonic()))
    return {'requested_commands':len(actions),'accepted_commands':sum(r['receipt']['accepted'] for r in rows),
            'last_receipt':rows[-1]['receipt'] if rows else None,'commands':rows}


def freeze(out,config):
    paths=[ROOT/'scripts/pcba.py',ROOT/'runtime/subscription.py',ROOT/'runtime/cli.py',
           ROOT/'runtime/envs.py',ROOT/'runtime/options.py',ROOT/'runtime/evaluation.py',ROOT/'environments/registry.json']
    paths+=list((ROOT/'environments/pcba').rglob('*'))+list(POLICY.rglob('*'))
    for path in sorted(paths):
        if not path.is_file() or '__pycache__' in path.parts:continue
        rel=path.relative_to(ROOT);payload=path.read_bytes()
        target=out/'source_snapshot'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
    write(out/'manifest.json',{'game':'pcba','mode':'actual_subscription_continuous_physics',
        'policy_kind':'general visual-language model emitting literal action chunks; no trained robot weights',
        'config':config,'direct_api_calls':0,'oracle_actions':False,
        'observations':'pixels, measured robot state, declared device switches and public static station calibration',
        'electrical_test':'mock','suction':'ideal proximity weld','video':'rendered after execution from native recorded states and wall timestamps; see replay.json'})


class Recorder:
    def __init__(self,env,out):
        self.env=env;self.out=out;self.frames=[];self.states=[];self.next_frame=0.
        (out/'frames').mkdir()

    def sample(self,force=False):
        if not force and time.monotonic()<self.next_frame:return
        # State capture is evaluator-only. Render replay after the live clock stops,
        # avoiding extra software-render stalls in the physics/control threads.
        with self.env.lock:
            if hasattr(self.env,'sync_snapshot'):self.env.sync_snapshot()
            state={k:getattr(self.env.data,k).copy() for k in ('qpos','qvel','ctrl','eq_active')}
            state['geom_rgba']=self.env.model.geom_rgba.copy()
            captured=float(self.env.data.time)
        self.states.append(state)
        name=f'frames/{len(self.frames):05d}.png'
        self.frames.append({'path':name,'simulation_time_s':captured,'wall_time':time.monotonic()})
        self.next_frame=time.monotonic()+.5

    def finish(self):
        write(self.out/'replay.json',{'frames':self.frames,'kind':'native samples; gaps show held prior camera frame'})
        if not self.frames:return
        np.savez_compressed(self.out/'recorded-states.npz',**{
            k:np.stack([state[k] for state in self.states]) for k in self.states[0]})
        model=mujoco.MjModel.from_xml_string(self.env.xml);data=mujoco.MjData(model)
        with mujoco.Renderer(model,height=480,width=640) as renderer:
            for index,(frame,state) in enumerate(zip(self.frames,self.states)):
                for k in ('qpos','qvel','ctrl','eq_active'):getattr(data,k)[:]=state[k]
                model.geom_rgba[:]=state['geom_rgba'];data.time=frame['simulation_time_s']
                mujoco.mj_forward(model,data);renderer.update_scene(data,camera='overview')
                Image.fromarray(renderer.render()).save(self.out/frame['path'])
                if index%100==0:print(f'Exporting native replay: {index+1}/{len(self.frames)} frames',flush=True)
        import imageio_ffmpeg
        fps=10
        writer=imageio_ffmpeg.write_frames(str(self.out/'replay.mp4'),(640,480),fps=fps,
            codec='libx264',pix_fmt_in='rgb24',pix_fmt_out='yuv420p',output_params=['-crf','24'])
        writer.send(None)
        try:
            start=self.frames[0]['wall_time'];end=self.frames[-1]['wall_time'];index=0
            pixels=np.array(Image.open(self.out/self.frames[0]['path']).convert('RGB'))
            for tick in range(max(1,math.ceil((end-start)*fps))):
                while index+1<len(self.frames) and self.frames[index+1]['wall_time']<=start+tick/fps:
                    index+=1;pixels=np.array(Image.open(self.out/self.frames[index]['path']).convert('RGB'))
                writer.send(pixels.tobytes())
        finally:writer.close()


def evaluate(output,*,seed=0,max_calls=24,duration=240.,ttl=12.,service_tier="priority"):
    from runtime.subscription import SubscriptionClient
    if type(max_calls) is not int or not 1<=max_calls<=100:raise ValueError('max_calls must be 1..100')
    if not math.isfinite(duration) or not 0<duration<=600:raise ValueError('duration must be 0..600 seconds')
    if not math.isfinite(ttl) or not 0<ttl<=15:raise ValueError('ttl must be 0..15 seconds')
    if service_tier not in ('ultrafast','priority','default'):raise ValueError('Unsupported service tier')
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    config={'seed':seed,'max_calls':max_calls,'duration_s':duration,'observation_ttl_s':ttl,
            'model':'gpt-6.1-sol','effort':'low','service_tier':service_tier,'control_dt_s':.05,'max_chunk_commands':120}
    freeze(out,config)
    env=PCBATestCell(seed=seed,asset_dir=out/'assets');client=None;session=None;pool=None
    stop=threading.Event();calls=[];memory='';previous=None;error=None;stop_reason='max_calls'
    recorder=Recorder(env,out);timing=None;future=None
    try:
        (out/'scene.xml').write_text(env.xml)
        # Warm all render views and authenticate BEFORE starting the live clock.
        env.observe(cameras=('overview','top','wrist'),width=640,height=480)
        client=SubscriptionClient(output=out/'transport',output_schema=json.loads((POLICY/'action.schema.json').read_text()),
            system=(POLICY/'system.txt').read_text(),auth_only_home=True,record_reasoning=False,service_tier=service_tier)
        pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pcba-policy')
        session=RealtimeSession(env).start();end=time.monotonic()+duration
        recorder.sample(force=True)
        for number in range(max_calls):
            if time.monotonic()>=end:stop_reason='wall_duration';break
            diag=env.diagnostics()
            if len(diag['sorted'])==BOARD_COUNT:stop_reason='environment_terminal';break
            if diag['dropped']:stop_reason='board_dropped';break
            directory=out/f'call-{number:03d}';directory.mkdir()
            captured_wall=time.monotonic()
            obs=env.observe(cameras=('overview','top','wrist'),width=640,height=480)
            public={k:v for k,v in obs.items() if k!='images'};write(directory/'observation.json',public)
            prompt=policy_prompt(obs,number,memory,previous,ttl)
            images=[]
            for pixels in obs['images'].values():
                buf=BytesIO();Image.fromarray(pixels).save(buf,format='PNG');images.append(buf.getvalue())
            row={'call':number,'source_time_s':obs['capture_time_s']};calls.append(row)
            future=pool.submit(client.act,prompt,images,directory/'model')
            while not future.done() and time.monotonic()<end:
                recorder.sample();time.sleep(.01)
            if not future.done():stop_reason='wall_duration_in_flight';break
            answer,meta=future.result();row['model_wall_seconds']=meta['wall_seconds'];row['token_usage']=meta['token_usage']
            try:d,actions=parse_decision(answer)
            except (ValueError,TypeError) as exc:
                previous={'accepted_commands':0,'last_receipt':{'accepted':False,'reason':'invalid_output','detail':str(exc)}}
                row['execution']=previous;write(directory/'execution.json',previous);continue
            row['summary']=d['summary'];memory=d['memory']
            with (directory/'actions.jsonl').open('w') as log:
                future=pool.submit(execute_chunk,env,actions,capture_time=obs['capture_time_s'],
                    capture_wall=captured_wall,ttl=ttl,stop=stop,log=log)
                while not future.done() and time.monotonic()<end:
                    recorder.sample();time.sleep(.01)
                if not future.done():stop.set()
                execution=future.result(timeout=5.)
            row['execution']=execution;write(directory/'execution.json',execution)
            previous={k:v for k,v in execution.items() if k!='commands'}
            print(json.dumps({'call':number,'latency_s':round(meta['wall_seconds'],3),'summary':d['summary'],
                  'accepted':execution['accepted_commands'],'requested':len(actions),'receipt':execution['last_receipt']},ensure_ascii=False),flush=True)
            if d['done']:stop_reason='model_claimed_done';break
    except KeyboardInterrupt:
        stop_reason='interrupted'
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc)};stop_reason='runner_error'
    finally:
        stop.set()
        if session:session.close();timing=session.timing()
        if client:client.close()
        if pool:pool.shutdown(wait=True,cancel_futures=True)
        recorder.sample(force=True)
        for camera in ('overview','top','wrist','racks_closeup'):
            obs=env.observe(cameras=(camera,),width=640,height=480)
            Image.fromarray(obs['images'][camera]).save(out/f'final-{camera}.png')
        diag=env.diagnostics()
        completed=sum(r['correct'] for r in diag['sorted'].values())
        commands=[cmd for c in calls for cmd in c.get('execution',{}).get('commands',[])]
        if timing:
            timing['wall_minus_sim_s']=timing['wall_elapsed_s']-timing['sim_elapsed_s']
            timing['timing_valid']=timing['max_tick_lag_s']<=.02 and abs(timing['wall_minus_sim_s'])<=max(.05,timing['wall_elapsed_s']*.01)
        metrics={'boards_total':BOARD_COUNT,'boards_picked':len({e['board'] for e in diag['events'] if e['kind']=='vacuum_attached'}),
            'tests_completed':len(diag['test_receipts']),'correctly_sorted':completed,
            'incorrectly_sorted':len(diag['sorted'])-completed,'success':completed==BOARD_COUNT and not diag['dropped'],
            'accepted_commands':sum(c['receipt']['accepted'] for c in commands),
            'rejected_commands':sum(not c['receipt']['accepted'] for c in commands),
            'expired_chunks':sum(c['receipt'].get('reason') in ('expired_wall_observation','stale_or_future_observation') for c in commands)}
        report={'kind':'actual_subscription_visual_action_baseline','direct_api_calls':0,'model_calls_attempted':len(calls),
            'model_calls_completed':sum('model_wall_seconds' in c for c in calls),'config':config,'metrics':metrics,
            'timing':timing,'stop_reason':stop_reason,'error':error,'calls':calls,'diagnostics':diag}
        save_report(out,report)
        (out/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in diag['events']))
        recorder.finish();env.close()
    print(json.dumps({'output':str(out),'metrics':metrics,'stop_reason':stop_reason,'error':error,'timing':timing},indent=2),flush=True)
    if error:raise RuntimeError(error['type']+': '+error['message'])
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    run=commands.add_parser('eval')
    run.add_argument('--output',type=Path,default=ROOT/'runs'/f'pcba-policy-{time.strftime("%Y%m%dT%H%M%S")}')
    run.add_argument('--provider',choices=['subscription'],default='subscription',help='Decision source (default: subscription)')
    run.add_argument('--seed',type=int,default=0)
    run.add_argument('--max-calls',type=int,default=24)
    run.add_argument('--service-tier',choices=['ultrafast','priority','default'],default='priority')
    run.add_argument('--wall-seconds',type=positive_float,default=240.,help='Wall-clock duration in seconds')
    run.add_argument('--ttl',type=float,default=12.)
    report=commands.add_parser('report')
    report.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='report':
        result=json.loads((args.output/'report.json').read_text())
        print(json.dumps({key:result[key] for key in ('kind','metrics','timing','stop_reason','error')},indent=2))
    else:
        with recording(args.output,game='pcba',command='eval',provider=args.provider,clock='wall',detail_file='report.json'):
            evaluate(args.output,seed=args.seed,max_calls=args.max_calls,duration=args.wall_seconds,ttl=args.ttl,service_tier=args.service_tier)
