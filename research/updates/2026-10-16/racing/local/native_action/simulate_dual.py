"""Strict native-action simulation: model decides; blind executor delivers."""
import sys,pathlib,argparse,json,time,heapq,random,math,collections,threading,concurrent.futures as cf,hashlib,subprocess,base64
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from run import Native,make_world,write,append,ROOT
from core.episode import Episode
from core.sport import FINISHED,UNIT_OVER,parse_action
from core.outcome import decide
from executor import Executor
import policy,recurrent,forecast
from session_native import SessionNative
p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--profile',type=pathlib.Path,required=True);p.add_argument('--variant',choices=policy.VARIANTS,default='predict');p.add_argument('--chunk',type=int,default=3);p.add_argument('--anchor',choices=['issue','arrival'],default='issue');p.add_argument('--history',type=int,default=3);p.add_argument('--memory',action='store_true');p.add_argument('--session',action='store_true');p.add_argument('--forecast',action='store_true');p.add_argument('--max-duration',type=float,default=1);p.add_argument('--camera',choices=['front','chase','dual'],default='front');p.add_argument('--cadence',type=float,default=.3);p.add_argument('--workers',type=int,default=4);p.add_argument('--capacity',type=int,default=8);p.add_argument('--seed',type=int,default=101);p.add_argument('--screen-seconds',type=float,default=18);p.add_argument('--slowdown',type=float,default=1);a=p.parse_args()
if a.max_duration not in (1,3) or (a.max_duration!=1 and (not a.session or a.forecast or a.memory)):p.error('long command validity requires a plain session controller')
if a.forecast and not a.session:p.error('--forecast requires --session')
if a.session and (a.capacity!=1 or a.workers!=1 or a.memory or a.anchor!='arrival'):p.error('--session requires --capacity1 --workers1 without --memory')
def observe(m,views):
 base={'step':m.k,'t_sim':round(m.k*m.dt,4),'phase':'over' if m.phase().state==FINISHED else 'review' if m.phase().state==UNIT_OVER else 'running','done':m.phase().state==FINISHED}
 cameras=['front','chase'] if a.camera=='dual' else [a.camera]
 frames=[views.view('A',base,query={'camera':c}) for c in cameras]
 return frames[-1]['state'],tuple(base64.b64decode(v['observation']['image_png_b64']) for v in frames)

a.out.mkdir(parents=True,exist_ok=False);profile=json.loads(a.profile.read_text());sport,cfg,m,views,spec=make_world(a.seed,1,a.slowdown)
config={k:str(v) if isinstance(v,pathlib.Path) else v for k,v in vars(a).items()};config.update(raw_camera_only=True,image_input_detail='auto',recurrent_sha256=hashlib.sha256(pathlib.Path(recurrent.__file__).read_bytes()).hexdigest(),adapter_sha256=hashlib.sha256(pathlib.Path(__file__).resolve().parents[1].joinpath('run.py').read_bytes()).hexdigest(),code_driving_policy=False,auth='chatgpt',api_cost_usd=0,future_answers_visible=False,policy_sha256=hashlib.sha256(pathlib.Path(policy.__file__).read_bytes()).hexdigest(),executor_sha256=hashlib.sha256(pathlib.Path(__file__).with_name('executor.py').read_bytes()).hexdigest(),profile_sha256=hashlib.sha256(a.profile.read_bytes()).hexdigest());write(a.out/'config.json',config)
(a.out/'run_snapshot.py').write_bytes(pathlib.Path(__file__).resolve().parents[1].joinpath('run.py').read_bytes())
for n in ['simulate.py','simulate_dual.py','policy.py','executor.py','recurrent.py','session_native.py','forecast.py']:(a.out/n).write_bytes(pathlib.Path(__file__).with_name(n).read_bytes())
ep=Episode(a.out/'episode.jsonl');ep.write('header',cfg=cfg.to_json(),sport=sport.name,revision=sport.revision,protocol='realtime',source_sha=None)
clients=[];lock=threading.Lock();local=threading.local();pool=cf.ThreadPoolExecutor(max_workers=a.workers)
def act(task,images,ident):
 write(a.out/f'decision_{ident:05d}'/'input.json',{'prompt':task,'image_sha256':[hashlib.sha256(x).hexdigest() for x in images]})
 if not hasattr(local,'client'):
  with lock:
   local.client=(SessionNative if a.session else Native)(a.out/f'worker_{len(clients)}');clients.append(local.client)
 validate=(lambda x:forecast.parse(x,a.chunk,a.anchor)[0]) if a.forecast else (lambda x:recurrent.parse(x,a.chunk,a.anchor)[0]) if a.memory else (lambda x:policy.parse(x,a.chunk,a.anchor,max_duration=a.max_duration))
 answer,meta=local.client.act(task,images,a.out/f'decision_{ident:05d}',validator=validate)
 try:
  prediction={}
  if a.forecast:commands,prediction=forecast.parse(answer,a.chunk,a.anchor);memory=scene=''
  elif a.memory:commands,memory,scene=recurrent.parse(answer,a.chunk,a.anchor)
  else:commands=policy.parse(answer,a.chunk,a.anchor,max_duration=a.max_duration);memory=scene=''
  invalid=False
 except (ValueError,TypeError) as e:commands=[];memory=scene='';prediction={};invalid=True;write(a.out/f'decision_{ident:05d}'/'rejection.json',{'error':str(e)})
 return {'commands':commands,'memory':memory,'scene':scene,'forecast':prediction,'invalid':invalid,**meta}
rng=random.Random(a.seed+1700);history=collections.deque(maxlen=a.history);executor=Executor();pending=[];seq=0;nextissue=0;lastseen=0;invalid=0;drops=0;stalled=0;samplecount=0;distance=0;started=time.monotonic();model_release=0;release_steps={};session_issues=0;last_memory='';past_commands=collections.deque(maxlen=16);summary={'status':'incomplete','api_cost_usd':0,'code_driving_policy':False}
try:
 while m.phase().state!=FINISHED and (not a.screen_seconds or m.k*m.dt<a.screen_seconds):
  if m.phase().state==UNIT_OVER:
   for _,_,_,f in pending:f.result()
   pending.clear();model_release=m.k;executor.clear();history.clear();last_memory='';past_commands.clear();ep.write('resume',k=m.k);m.resume();nextissue=m.k
  ready=[]
  while pending and pending[0][0]<=m.k:ready.append(heapq.heappop(pending))
  if ready:
   if a.session:model_release=max(release_steps.pop(r[1]) for r in ready)
   results={r[1]:r[3].result() for r in ready}
   for due,ident,seen,f in ready:append(a.out/'arrivals.jsonl',{'seq':ident,'due_step':due,'seen_step':seen,**results[ident]})
   due,ident,seen,_=max(ready,key=lambda x:x[1]);result=results[ident];invalid+=sum(r['invalid'] for r in results.values())
   if executor.offer(result['commands'],seen*m.dt,m.k*m.dt,ident,a.anchor):lastseen=seen;last_memory=result['memory']
  cmd=executor.due(m.k*m.dt)
  if cmd is not None:
   cmd=parse_action(sport.action_layer('low'),'A',cmd,m,{});ep.write('cmd',k=m.k,seat='A',cmd=cmd,seen=lastseen);m.apply('A',cmd);past_commands.append({'t':m.k*m.dt,'command':cmd});append(a.out/'applied.jsonl',{'step':m.k,'seq':executor.seq,'command':cmd})
  if m.k>=nextissue:
   nextissue=m.k+max(1,round(a.cadence/m.dt))
   state,image=observe(m,views);state=policy.visible(state);history.append((state,image));speed=state['own']['forward_speed'];stalled+=abs(speed)<.15;samplecount+=1;distance+=abs(speed)*a.cadence
   if len(pending)>=a.capacity or (a.session and m.k<model_release):drops+=1
   else:
    if a.session:task=(forecast.prompt if a.forecast else policy.session_prompt)([x[0] for x in history],a.variant,a.chunk,a.anchor,{k:profile[k] for k in ['p50','p95','mean']},a.slowdown,camera=a.camera,committed=executor.timeline,first=session_issues==0,**({'max_duration':a.max_duration} if not a.forecast else {}));session_issues+=1
    else:task=(recurrent.prompt if a.memory else policy.prompt)([x[0] for x in history],a.variant,a.chunk,a.anchor,{k:profile[k] for k in ['p50','p95','mean']},a.slowdown,camera=a.camera,committed=executor.timeline,**({'memory':last_memory,'past_commands':past_commands} if a.memory else {}))
    sample=rng.randrange(len(profile['delays']));delay=profile['delays'][sample];drain=profile.get('drain_delays',profile['delays'])[sample];due=m.k+max(1,math.ceil(delay/a.slowdown/m.dt));release_steps[seq]=m.k+max(1,math.ceil(drain/a.slowdown/m.dt));f=pool.submit(act,task,[image for x in history for image in x[1]],seq);heapq.heappush(pending,(due,seq,m.k,f));append(a.out/'issued.jsonl',{'seq':seq,'seen_step':m.k,'due_step':due,'sampled_delay':delay,'sampled_drain_delay':drain,'release_step':release_steps[seq]});seq+=1
    if seq%20==0:print(json.dumps({'seq':seq,'game_s':round(m.k*m.dt,2),'wall_s':round(time.monotonic()-started,1),'variant':a.variant}),flush=True)
  m.step()
 complete=m.phase().state==FINISHED;ep.write('end',k=m.k,reason='match_over' if complete else 'screening_prefix_only')
 for _,_,_,f in pending:f.result()
 state,image=observe(m,views);(a.out/'last_camera.png').write_bytes(image[-1])
 summary.update(status='complete' if complete else 'screening_prefix',seed=a.seed,variant=a.variant,game_seconds=m.k*m.dt,calls=seq,invalid_outputs=invalid,drops=drops,skipped_inference_slots=drops,wall_seconds=time.monotonic()-started,stalled_observation_fraction=stalled/max(1,samplecount),own_speed_integral_m=distance,public_final_state=policy.visible(state),digest=m.state_digest())
 if complete:summary.update(won=decide(m,sides=['A','opponent']).winner=='A',scores=m.scores())
 r=subprocess.run([sys.executable,'-m','core.episode',str(ROOT/'sports/racing/plugin.py'),str(a.out)],cwd=ROOT,capture_output=True,text=True)
 if r.returncode:raise RuntimeError('independent replay failed:'+r.stderr[-300:])
 check=json.loads((a.out/'replay_check.json').read_text());summary['replay_matches']=check['state_sha']==m.state_digest();assert summary['replay_matches']
except BaseException as e:summary.update(error=type(e).__name__+':'+str(e));raise
finally:
 write(a.out/'summary.json',summary);pool.shutdown(wait=True,cancel_futures=True)
 for client in clients:client.close()
print('RESULT '+json.dumps(summary),flush=True)
