"""Real wall-clock API validation. Raw camera -> GPT actuator rows -> blind timer."""
import argparse,base64,collections,concurrent.futures as cf,getpass,json,os,pathlib,signal,socket,subprocess,sys,threading,time
import requests
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from run import API,Budget,MODEL,MINIMAL_SYSTEM,ROOT,WORK_ROOT,write,append
from executor import Executor
import policy,forecast

def free_port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--profile',type=pathlib.Path,required=True);p.add_argument('--seed',type=int,default=401);p.add_argument('--variant',choices=policy.VARIANTS,default='calibrated');p.add_argument('--camera',choices=['front','chase'],default='chase');p.add_argument('--history',type=int,default=3);p.add_argument('--chunk',type=int,default=3);p.add_argument('--anchor',choices=['issue','arrival'],default='issue');p.add_argument('--cadence',type=float,default=.3);p.add_argument('--capacity',type=int,default=4);p.add_argument('--session',action='store_true');p.add_argument('--forecast',action='store_true');p.add_argument('--max-duration',type=float,choices=[1,3],default=1);p.add_argument('--stage-cap',type=float,default=9);p.add_argument('--budget',type=pathlib.Path,default=WORK_ROOT/'research-results/budget.json');a=p.parse_args()
 if a.session and (a.capacity!=1 or a.anchor!='arrival'):p.error('stateful validation requires capacity1 and arrival anchoring')
 if a.forecast and (not a.session or a.max_duration!=1):p.error('forecast requires session and max-duration1')
 if a.max_duration!=1 and not a.session:p.error('long validity requires session')
 a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False);data=a.out/'service';data.mkdir();profile=json.loads(a.profile.read_text());budget=Budget(a.budget,cache_aware=True)
 write(a.out/'config.json',{**{k:str(v) if isinstance(v,pathlib.Path) else v for k,v in vars(a).items()},'raw_camera_only':True,'code_driving_policy':False,'slowdown':1,'artificial_delay':False})
 for name in ['live.py','policy.py','executor.py','forecast.py']:(a.out/name).write_bytes(pathlib.Path(__file__).with_name(name).read_bytes())
 (a.out/'run_snapshot.py').write_bytes(pathlib.Path(__file__).resolve().parents[1].joinpath('run.py').read_bytes())
 key=getpass.getpass('API credential (memory only): ');gameport=free_port();proxyport=free_port();processes=[];clients=[];local=threading.local();lock=threading.Lock();wake=threading.Event();pool=cf.ThreadPoolExecutor(max_workers=a.capacity)
 env=dict(os.environ);env.update(MUJOCO_GL='egl',LP_NUM_THREADS='1',RCB_DATA=str(data),RO_PLUGIN=str(ROOT/'sports/racing/plugin.py'),RO_SPORT='racing',RO_FORMAT='match',RO_SEATS='A',RO_SEED=str(a.seed),RO_LEVEL='1',RO_FIRST='A',RO_SLOWDOWN='1',RCB_ACTION_LEVEL='low',RCB_PLAY='program',RCB_ACT_RULE='program',RCB_PLAYER_MODE='model',RCB_PORT=str(gameport),RCB_RENDER_VIDEO='0',RCB_BROADCAST='0')
 proxyenv=dict(env);proxyenv.update(THINK_UPSTREAM='https://api.openai.com',OPENROUTER_API_KEY=key,THINK_MODEL=MODEL,THINK_USAGE_FILE=str(data/'think_usage_A.json'),THINK_CALLS_FILE=str(data/'think_calls_A.jsonl'),THINK_RATE_LIMIT_RETRIES='0');key=None
 http=requests.Session();last_http=0;drains=[];pending={};issued={};seq=0;history=collections.deque(maxlen=a.history);executor=Executor();summary={'status':'incomplete','code_driving_policy':False};startwall=None;submitted=0;session_issues=0
 def call(endpoint,body=None):
  nonlocal last_http
  time.sleep(max(0,.06-(time.monotonic()-last_http)));last_http=time.monotonic();url=f'http://127.0.0.1:{gameport}/A/'+endpoint
  r=http.get(url,timeout=30) if body is None else http.post(url,json=body,timeout=30)
  append(a.out/'http_requests.jsonl',{'endpoint':endpoint,'wall_monotonic':last_http,'elapsed_seconds':time.monotonic()-last_http,'http_status':r.status_code})
  if r.status_code==409 and endpoint in ('act','observe') and r.json().get('now',{}).get('phase') in ('review','over'):return r.json()
  if r.status_code!=200:raise RuntimeError(f'game {endpoint} HTTP {r.status_code}')
  return r.json()
 def infer(task,images,ident,pub=None):
  if not hasattr(local,'client'):
   with lock:
    local.client=API('local-meter-placeholder',budget,'native_validation',a.stage_cap,f'http://127.0.0.1:{proxyport}/v1/responses',instructions=MINIMAL_SYSTEM,image_detail='auto',stateful=a.session);clients.append(local.client)
  target=a.out/f'decision_{ident:05d}';write(target/'input.json',{'prompt':task})
  def publish(rows,meta):
   if pub is not None and not pub.done():pub.set_result((rows,meta));wake.set()
  validate=(lambda x:forecast.parse(x,a.chunk,a.anchor)[0]) if a.forecast else (lambda x:policy.parse(x,a.chunk,a.anchor,max_duration=a.max_duration))
  answer,meta=local.client.act(task,images,target,on_ready=publish if pub is not None else None,validator=validate)
  try:rows=validate(answer)
  except (ValueError,TypeError) as e:write(target/'rejection.json',{'error':str(e)});rows=[]
  return rows,meta
 def submit(task,images,ident):
  pub=cf.Future()
  def worker():
   try:
    result=infer(task,images,ident,pub)
    if not pub.done():pub.set_result(result);wake.set()
    return result
   except BaseException as e:
    if not pub.done():pub.set_exception(e);wake.set()
    raise
  drains.append(pool.submit(worker));return pub
 def audit(wait=False):
  for f in list(drains):
   if wait or f.done():f.result();drains.remove(f)
 def task():
  common=dict(camera=a.camera,committed=executor.timeline)
  if a.session:
   common['first']=session_issues==0
   if not a.forecast:common['max_duration']=a.max_duration
  return (forecast.prompt if a.forecast else policy.session_prompt if a.session else policy.prompt)([s for s,_ in history],a.variant,a.chunk,a.anchor,{k:profile[k] for k in ['p50','p95','mean']},**common)
 try:
  for name,cmd,e in [('proxy',[sys.executable,str(ROOT/'players/metering/think_proxy.py'),str(proxyport)],proxyenv),('service',[sys.executable,'-m','core.serve'],env)]:
   log=(a.out/(name+'.log')).open('w');processes.append((subprocess.Popen(cmd,cwd=ROOT,env=e,stdout=log,stderr=subprocess.STDOUT,start_new_session=True),log))
  proxyenv.pop('OPENROUTER_API_KEY',None)
  for _ in range(120):
   if any(pr.poll() is not None for pr,_ in processes):raise RuntimeError('service or proxy exited')
   try:call('status');break
   except (requests.RequestException,RuntimeError):time.sleep(.25)
  else:raise RuntimeError('service did not start')
  write(a.out/'spec.json',call('spec'));v=call('observe',{'query':{'camera':a.camera}});history.append((policy.visible(v['now']),base64.b64decode(v['observation']['image_png_b64'])))
  # Canonical metering requires a model request before start. Discard its output;
  # no precomputed command gets an artificial zero-latency start advantage.
  infer(task(),[history[-1][1]],seq);seq+=1;history.clear();call('start',{});startwall=time.monotonic();nextissue=startwall
  while True:
   audit();wake.clear();status=call('status');state=status.get('state',status.get('now',status))
   if state.get('done') or state.get('race_over'):break
   if state.get('awaiting_review') or state.get('world')=='frozen' or state.get('phase')=='review':
    audit(wait=True)
    for f in pending.values():f.result()
    pending.clear();history.clear();executor.clear();call('ready',{'why':'Reviewed referee outcome.','plan':'Continue frozen raw-camera GPT actuator policy.'});nextissue=time.monotonic();continue
   t=float(state['t_sim']);ready=[i for i,f in pending.items() if f.done()]
   if ready:
    results={i:pending.pop(i).result() for i in ready};chosen=max(ready);rows,meta=results[chosen]
    accepted=executor.offer(rows,issued[chosen],t,chosen,a.anchor)
    for i in ready:append(a.out/'arrivals.jsonl',{'seq':i,'issued_game_time':issued[i],'arrival_game_time':t,'selected':i==chosen and accepted,'commands':results[i][0],**results[i][1]})
   cmd=executor.due(t)
   if cmd is not None:
    r=call('act',cmd);append(a.out/'applied.jsonl',{'seq':executor.seq,'game_time':t,'command':cmd,'took_effect':r.get('took_effect')});submitted+=1
   now=time.monotonic()
   if now>=nextissue:
    nextissue=now+a.cadence;v=call('observe',{'query':{'camera':a.camera}});s=policy.visible(v['now'])
    if s.get('done') or s.get('phase')=='review':continue
    history.append((s,base64.b64decode(v['observation']['image_png_b64'])))
    # Stateful conversation cannot see a not-yet-drained prior response.
    if len(pending)<a.capacity and (not a.session or not drains):
     issued[seq]=float(s['t_sim']);append(a.out/'issued.jsonl',{'seq':seq,'game_time':issued[seq]});pending[seq]=submit(task(),[im for _,im in history],seq);seq+=1;session_issues+=1
   wake.wait(.02)
  audit(wait=True)
  for f in pending.values():f.result()
  os.kill(processes[-1][0].pid,signal.SIGUSR1)
  for _ in range(240):
   f=data/'final.json';final=json.loads(f.read_text()) if f.exists() else {}
   if final.get('graded_ready'):break
   time.sleep(.25)
  else:raise RuntimeError('service replay did not finalize')
  summary.update(status='complete',won=final.get('match_winner')=='A',match_winner=final.get('match_winner'),valid_trial=final.get('valid_trial'),deterministic=final.get('deterministic'),sim_lag=final.get('sim_lag'),wall_seconds=time.monotonic()-startwall,calls=seq,submitted_commands=submitted,model=MODEL,service_tier='ultrafast',artificial_delay=False,slowdown=1)
 except BaseException as e:summary['error']=type(e).__name__+':'+str(e);raise
 finally:
  write(a.out/'summary.json',summary)
  # Stop physics immediately on failure, then drain/account every issued API call.
  for pr,log in reversed(processes):
   if pr.poll() is None:
    os.killpg(pr.pid,signal.SIGTERM)
    try:pr.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(pr.pid,signal.SIGKILL);pr.wait()
   log.close()
  pool.shutdown(wait=True,cancel_futures=True)
  for client in clients:client.close()
 print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
