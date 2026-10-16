"""Frozen-policy real API validation using the repository's real HTTP service/meter.

No artificial model delay, no paused physics during decisions. The canonical proxy
is configured with THINK_UPSTREAM=https://api.openai.com (its compatibility env
variable for the credential is called OPENROUTER_API_KEY; no OpenRouter is used).
"""
import argparse,collections,concurrent.futures as cf,getpass,json,os,pathlib
import signal,socket,subprocess,sys,threading,time
import requests
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from run import WORK_ROOT,API,Budget,MODEL,MINIMAL_SYSTEM,ROOT,parse,controller_prompt,schedule_commands,write,append,camera_metrics
from waypoints import Ego,Tracker,parse_points
from lane import Lane,parse_lane
from explained_api import ExplainedAPI
API=ExplainedAPI
_BaseBudget=Budget
class Budget(_BaseBudget):
 def __init__(self,path):super().__init__(path,cache_aware=True)

def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--profile',type=pathlib.Path,required=True)
 p.add_argument('--seed',type=int,default=101);p.add_argument('--level',type=int,default=1);p.add_argument('--slowdown',type=float,default=1)
 p.add_argument('--variant',default='basic');p.add_argument('--chunk',type=int,default=1);p.add_argument('--history',type=int,default=1)
 p.add_argument('--cadence',type=float,default=.3);p.add_argument('--capacity',type=int,default=8);p.add_argument('--budget',type=pathlib.Path,default=WORK_ROOT/'research-results/budget.json')
 p.add_argument('--control',choices=['servo','waypoint','lane'],default='servo');p.add_argument('--anchor',choices=['arrival','issue'],default='arrival')
 p.add_argument('--executor-preflight',action='store_true',help='FREE camera-reference HTTP executor test, NOT GPT and NOT API validation')
 p.add_argument('--validation-cap',type=float,default=18,help='Validation stage ceiling; the shared $30 total ceiling is always enforced')
 a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
 if a.executor_preflight and a.control not in ('waypoint','lane'):p.error('executor-preflight requires --control waypoint or lane')
 write(a.out/'config.json',{k:str(v) if isinstance(v,pathlib.Path) else v for k,v in vars(a).items()})
 for name in ['live.py','run.py','waypoints.py','lane.py']:
  (a.out/(name.removesuffix('.py')+'_snapshot.py')).write_bytes((WORK_ROOT/name).read_bytes())
 (a.out/'live_explained_snapshot.py').write_bytes(pathlib.Path(__file__).read_bytes())
 (a.out/'explained_api_snapshot.py').write_bytes(pathlib.Path(__file__).with_name('explained_api.py').read_bytes())
 key=None if a.executor_preflight else getpass.getpass('API credential for real-time verification (memory only): ')
 data=a.out/'service';data.mkdir();gameport=port();proxyport=port();procs=[];clients=[];local=threading.local();clientlock=threading.Lock()
 profile=json.loads(a.profile.read_text());budget=Budget(a.budget)
 env=dict(os.environ);env.update(MUJOCO_GL='egl',LP_NUM_THREADS='1',RCB_DATA=str(data),RO_PLUGIN=str(ROOT/'sports/racing/plugin.py'),RO_SPORT='racing',RO_FORMAT='match',RO_SEATS='A',RO_SEED=str(a.seed),RO_LEVEL=str(a.level),RO_FIRST='A',RO_SLOWDOWN=str(a.slowdown),RCB_ACTION_LEVEL='low',RCB_PLAY='program',RCB_ACT_RULE='program',RCB_PLAYER_MODE='model',RCB_PORT=str(gameport),RCB_RENDER_VIDEO='0',RCB_BROADCAST='0')
 if a.executor_preflight:env['RCB_PLAYER_MODE']='oracle'
 proxyenv=dict(env);proxyenv.update(THINK_UPSTREAM='https://api.openai.com',OPENROUTER_API_KEY=key,THINK_MODEL=MODEL,THINK_USAGE_FILE=str(data/'think_usage_A.json'),THINK_CALLS_FILE=str(data/'think_calls_A.jsonl'),THINK_RATE_LIMIT_RETRIES='0')
 launches=[('service',[sys.executable,'-m','core.serve'],env)]
 if not a.executor_preflight:launches.insert(0,('proxy',[sys.executable,str(ROOT/'players/metering/think_proxy.py'),str(proxyport)],proxyenv))
 for name,cmd,e in launches:
  log=(a.out/(name+'.log')).open('w');procs.append((subprocess.Popen(cmd,cwd=ROOT,env=e,stdout=log,stderr=subprocess.STDOUT,start_new_session=True),log))
 # Remove additional copies from parent environment dictionaries after spawn.
 proxyenv.pop('OPENROUTER_API_KEY',None);key=None
 base=f'http://127.0.0.1:{gameport}/A';endpoint=f'http://127.0.0.1:{proxyport}/v1/responses'
 http=requests.Session();pool=cf.ThreadPoolExecutor(max_workers=a.capacity);last_http=0
 def call(ep,body=None):
  nonlocal last_http
  # All game requests are serial and separated by >=60ms: below the seat's
  # 20/sec limit even when status, observe and waypoint act requests coincide.
  time.sleep(max(0,.06-(time.monotonic()-last_http)));last_http=time.monotonic()
  r=http.get(base+'/'+ep,timeout=30) if body is None else http.post(base+'/'+ep,json=body,timeout=30)
  append(a.out/'http_requests.jsonl',{'endpoint':ep,'wall_monotonic':last_http,'elapsed_seconds':time.monotonic()-last_http,'http_status':r.status_code})
  if r.status_code==409 and ep in ('act','observe') and r.json().get('now',{}).get('phase') in ('review','over'):return r.json()
  if r.status_code!=200:raise RuntimeError(f'game {ep} HTTP {r.status_code}')
  return r.json()
 def infer(prompt,images,ident,publication=None):
  if a.executor_preflight:
   # Pixel-only reference planner for exercising the HTTP/clock adapter. Never
   # instantiated as API or Native, and never counted as GPT performance.
   s=json.JSONDecoder().raw_decode(prompt.split('Visible observations: ',1)[1])[0][-1]
   path=s['camera_measurements'].get('ground_path',[]);lane=.38 if s['own']['grid_side']=='inner' else -.38
   points=[]
   for x in [2,4,5]:
    if path:px,py=min(path,key=lambda p:abs(p[0]-x));points.append([px,max(-5,min(5,py+lane)),3.0])
    else:points.append([-1,.3,-.6])
   if a.control=='lane':points=[[3.2,lane,2.0]]
   time.sleep(profile['delays'][ident%len(profile['delays'])])
   meta={'auth':'camera-reference-executor-preflight-NOT-GPT','api_cost_usd':0,'artificial_delay':True,'invalid_output':False}
   write(a.out/f'decision_{ident:05d}'/'result.json',{'answer':json.dumps(points),**meta})
   return points,meta
  if not hasattr(local,'client'):
   with clientlock:
    client=API('local-meter-placeholder',budget,'validation',a.validation_cap,endpoint,instructions=MINIMAL_SYSTEM);clients.append(client)
   local.client=client
  target=a.out/f'decision_{ident:05d}'
  validate=lambda answer: parse_lane(answer,a.chunk) if a.control=='lane' else parse_points(answer,a.chunk) if a.control=='waypoint' else parse(answer,a.chunk)
  def publish(commands,meta):
   if publication is not None and not publication.done():publication.set_result((commands,meta));wake.set()
  answer,meta=local.client.act(prompt,images,target,on_ready=publish if publication is not None else None,validator=validate)
  try:commands=validate(answer)
  except (ValueError,TypeError) as e:
   write(target/'rejection.json',{'error':str(e),'fallback':'brake until next valid GPT plan'})
   return [],{**meta,'invalid_output':True}
  return commands,{**meta,'invalid_output':False}
 drains=[];wake=threading.Event()
 def submit(prompt,images,ident):
  publication=cf.Future()
  def worker():
   try:
    result=infer(prompt,images,ident,publication)
    if not publication.done():publication.set_result(result);wake.set()
    return result
   except BaseException as e:
    if not publication.done():publication.set_exception(e);wake.set()
    raise
  drains.append(pool.submit(worker))
  return publication
 def audit(wait=False):
  for f in list(drains):
   if wait or f.done():f.result();drains.remove(f)
 pending={};history=collections.deque(maxlen=a.history);seq=0;last=-1;plan=[];currentheat=None;nextissue=0;laststate=None;applied=[];submitted=0;summary={'status':'incomplete','driver':'camera-reference-executor-preflight-NOT-GPT' if a.executor_preflight else 'real-api'}
 ego=Ego();tracker=Lane() if a.control=='lane' else Tracker(ego);last_odo=None;odo_command=0;origins={};issued={};nextcontrol=0;crashes=0;invalid_before=-1
 def receive(s):
  nonlocal last_odo,odo_command,crashes,invalid_before
  t=float(s['t_sim']);own=s['own']
  if last_odo is not None:ego.update(own['forward_speed'],odo_command,max(0,t-last_odo))
  last_odo=t;odo_command=own['command'][1]
  count=len(s.get('crashes_this_heat',[]))
  if count>crashes:tracker.clear();invalid_before=t
  crashes=count
  return t
 def task(states):
  return controller_prompt(states,a.variant,a.chunk,{k:profile[k] for k in ['p50','p95','mean']},a.slowdown,a.control,a.anchor,tracker.local_points())
 try:
  for _ in range(120):
   if all(pr.poll() is None for pr,_ in procs):
    try:call('status');break
    except (requests.RequestException,RuntimeError):time.sleep(.25)
   else:raise RuntimeError('live service or metering proxy exited')
  else:raise RuntimeError('live service did not start')
  public_spec=call('spec');write(a.out/'spec.json',public_spec)
  # One metered pre-start model request establishes the canonical live model session.
  v=call('observe',{});s=v['now'];import base64
  ims=[base64.b64decode(v['observation']['image_png_b64'])]
  if a.variant=='metric':s['camera_measurements']=camera_metrics(ims[0],public_spec)
  infer(task([s]),ims,seq);seq+=1
  call('start',{});startwall=time.monotonic();nextissue=startwall
  while True:
   audit();wake.clear()
   status=call('observe',{}) if a.control=='lane' else call('status');state=status.get('state',status.get('now',status));laststate=state
   if state.get('done') or state.get('race_over'):break
   if state.get('awaiting_review') or state.get('world')=='frozen' or state.get('phase')=='review':
    audit(wait=True)
    for f in pending.values():f.result()
    pending.clear();history.clear();plan.clear();ego=Ego();tracker=Lane() if a.control=='lane' else Tracker(ego);last_odo=None;crashes=0;invalid_before=-1;nextcontrol=0
    call('ready',{'why':'Reviewed completed heat and current referee outcome.','plan':'Continue the frozen camera-driven policy.'})
    nextissue=time.monotonic();currentheat=None;continue
   game_time=receive(state);now=time.monotonic()
   if a.control=='lane':fresh=base64.b64decode(status['observation']['image_png_b64'])
   ready=[i for i,f in pending.items() if f.done()]
   if ready:
    results={i:pending.pop(i).result() for i in ready};chosen=max(ready)
    for i in ready:append(a.out/'response_arrivals.jsonl',{'seq':i,'observed_game_time':issued[i],'arrival_game_time':game_time,'arrival_wall_monotonic':time.monotonic(),'newest_in_batch':i==chosen,'older_than_already_applied':i<=last,'commands':results[i][0],**results[i][1]})
    if chosen>last:
     last=chosen;commands,meta=results[chosen];plan=[]
     if meta.get('invalid_output'):
      tracker.clear();tracker.seq=chosen;tracker.seen=round(issued[chosen]/.01)
      plan=[(game_time,{'type':'none'},chosen)]
     elif a.control in ('waypoint','lane'):
      if issued[chosen]>=invalid_before:tracker.offer(commands,origins[chosen],issued[chosen],chosen,round(issued[chosen]/.01))
     else:
      plan=[(k*.01,cmd,chosen) for k,cmd in schedule_commands(commands,round(issued[chosen]/.01),round(game_time/.01),.01,a.anchor)]
   if a.control in ('waypoint','lane') and game_time>=nextcontrol:
    nextcontrol=max(nextcontrol+.2,game_time) if a.control=='lane' else game_time+.1
    if a.control=='lane':
     cmd=tracker.drive(game_time,camera_metrics(fresh,public_spec))
    else:cmd=tracker.drive(game_time,state['own']['forward_speed'])
    r=call('act',cmd)
    append(a.out/'waypoint_actions.jsonl',{'model_seq':tracker.seq,'seen_step':tracker.seen,'game_time':game_time,'command':cmd,'estimated_ego':ego.pose(),'remaining_destinations':tracker.local_points(),'took_effect':r.get('took_effect')})
    if r.get('now',{}).get('own'):receive(r['now'])
    submitted+=1
    if r.get('took_effect') is not None:applied.append(tracker.seq)
   if plan and plan[0][0]<=game_time:
    _,cmd,ident=plan.pop(0);r=call('act',cmd);append(a.out/'applied.jsonl',{'seq':ident,'wall':now-startwall,'command':cmd,'took_effect':r.get('took_effect')});submitted+=1
    if r.get('took_effect') is not None:applied.append(ident)
   if now>=nextissue:
    nextissue=now+a.cadence*a.slowdown
    if len(pending)<a.capacity:
     v=status if a.control=='lane' else call('observe',{});s=v['now']
     if s.get('done') or s.get('phase')=='review':continue
     observed_time=receive(s);image=base64.b64decode(v['observation']['image_png_b64'])
     if a.variant=='metric':s['camera_measurements']=camera_metrics(image,public_spec)
     history.append((s,image))
     prompt=task([x[0] for x in history]);origins[seq]=ego.pose();issued[seq]=observed_time
     append(a.out/'issued.jsonl',{'seq':seq,'seen_step':s['step'],'game_time':observed_time,'origin_ego':origins[seq] if a.control=='waypoint' else None})
     write(a.out/f'decision_{seq:05d}'/'input.json',{'prompt':prompt})
     pending[seq]=submit(prompt,[x[1] for x in history],seq);seq+=1
   # The global HTTP gate already limits requests. A second 100ms sleep was
   # unnecessarily reducing raw-speed waypoint tracking to roughly 4.5Hz.
   wake.wait(.01 if a.control in ('waypoint','lane') else .1)
  audit(wait=True)
  for f in pending.values():f.result()
  svc=procs[-1][0];os.kill(svc.pid,signal.SIGUSR1)
  for _ in range(240):
   final=json.loads((data/'final.json').read_text())
   if final.get('graded_ready'):break
   time.sleep(.25)
  else:raise RuntimeError('live service replay did not finalize')
  summary={'status':'complete','match_winner':final.get('match_winner'),'won':final.get('match_winner')=='A','valid_trial':final.get('valid_trial'),'deterministic':final.get('deterministic'),'sim_lag':final.get('sim_lag'),'slowdown':a.slowdown,'calls':seq,'submitted_commands':submitted,'applied_commands':len(applied),'invalid_output_count':len(list(a.out.glob('decision_*/rejection.json'))),'control':a.control,'anchor':a.anchor,'system':'minimal','wall_seconds':time.monotonic()-startwall,'model':MODEL,'service_tier':'ultrafast','artificial_delay':False,'harbor_isolation':False,'decision_summaries_from_same_API_response':True,'cadence_seconds':a.cadence,'image_detail':'low','controller':'unchanged lane-commit visual tracker'}
  if a.executor_preflight:summary.update(driver='camera-reference-executor-preflight-NOT-GPT',api_cost_usd=0,model=None,service_tier=None,artificial_delay=True,system=None)
  write(a.out/'summary.json',summary);print(json.dumps(summary),flush=True)
 except BaseException as e:summary.update(error=type(e).__name__+': '+str(e));raise
 finally:
  write(a.out/'summary.json',summary)
  pool.shutdown(wait=True,cancel_futures=True)
  for c in clients:c.close()
  for pr,log in reversed(procs):
   if pr.poll() is None:
    os.killpg(pr.pid,signal.SIGTERM)
    try:pr.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(pr.pid,signal.SIGKILL);pr.wait()
   log.close()

if __name__=='__main__':main()
