"""Frozen-policy real API validation using the repository's real HTTP service/meter.

No artificial model delay, no paused physics during decisions. The canonical proxy
is configured with THINK_UPSTREAM=https://api.openai.com (its compatibility env
variable for the credential is called OPENROUTER_API_KEY; no OpenRouter is used).
"""
import argparse,collections,concurrent.futures as cf,getpass,json,os,pathlib
import signal,socket,subprocess,sys,threading,time
import requests
from run import API,Budget,MODEL,ROOT,parse,prompt_for,write,append,camera_metrics

def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--profile',type=pathlib.Path,required=True)
 p.add_argument('--seed',type=int,default=101);p.add_argument('--level',type=int,default=1);p.add_argument('--slowdown',type=float,default=1)
 p.add_argument('--variant',default='basic');p.add_argument('--chunk',type=int,default=1);p.add_argument('--history',type=int,default=1)
 p.add_argument('--cadence',type=float,default=.3);p.add_argument('--capacity',type=int,default=8);p.add_argument('--budget',type=pathlib.Path,default=ROOT/'research-results/budget.json')
 a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
 key=getpass.getpass('API credential for real-time verification (memory only): ')
 data=a.out/'service';data.mkdir();gameport=port();proxyport=port();procs=[];clients=[];local=threading.local();clientlock=threading.Lock()
 profile=json.loads(a.profile.read_text());budget=Budget(a.budget)
 env=dict(os.environ);env.update(MUJOCO_GL='egl',LP_NUM_THREADS='1',RCB_DATA=str(data),RO_PLUGIN=str(ROOT/'sports/racing/plugin.py'),RO_SPORT='racing',RO_FORMAT='match',RO_SEATS='A',RO_SEED=str(a.seed),RO_LEVEL=str(a.level),RO_FIRST='A',RO_SLOWDOWN=str(a.slowdown),RCB_ACTION_LEVEL='low',RCB_PLAY='program',RCB_ACT_RULE='program',RCB_PLAYER_MODE='model',RCB_PORT=str(gameport),RCB_RENDER_VIDEO='0',RCB_BROADCAST='0')
 proxyenv=dict(env);proxyenv.update(THINK_UPSTREAM='https://api.openai.com',OPENROUTER_API_KEY=key,THINK_MODEL=MODEL,THINK_USAGE_FILE=str(data/'think_usage_A.json'),THINK_CALLS_FILE=str(data/'think_calls_A.jsonl'),THINK_RATE_LIMIT_RETRIES='0')
 for name,cmd,e in [('proxy',[sys.executable,str(ROOT/'players/metering/think_proxy.py'),str(proxyport)],proxyenv),('service',[sys.executable,'-m','core.serve'],env)]:
  log=(a.out/(name+'.log')).open('w');procs.append((subprocess.Popen(cmd,cwd=ROOT,env=e,stdout=log,stderr=subprocess.STDOUT,start_new_session=True),log))
 # Remove additional copies from parent environment dictionaries after spawn.
 proxyenv.pop('OPENROUTER_API_KEY',None);key=None
 base=f'http://127.0.0.1:{gameport}/A';endpoint=f'http://127.0.0.1:{proxyport}/v1/responses'
 http=requests.Session();pool=cf.ThreadPoolExecutor(max_workers=a.capacity)
 def call(ep,body=None):
  r=http.get(base+'/'+ep,timeout=30) if body is None else http.post(base+'/'+ep,json=body,timeout=30)
  if r.status_code==409 and ep in ('act','observe') and r.json().get('now',{}).get('phase') in ('review','over'):return r.json()
  if r.status_code!=200:raise RuntimeError(f'game {ep} HTTP {r.status_code}')
  return r.json()
 def infer(prompt,images,ident):
  if not hasattr(local,'client'):
   with clientlock:
    client=API('local-meter-placeholder',budget,'validation',18,endpoint);clients.append(client)
   local.client=client
  answer,meta=local.client.act(prompt,images,a.out/f'decision_{ident:05d}');return parse(answer,a.chunk),meta
 pending={};history=collections.deque(maxlen=a.history);seq=0;last=-1;plan=[];currentheat=None;nextissue=0;laststate=None;applied=[];summary={'status':'incomplete'}
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
  infer(prompt_for([s],a.variant,a.chunk,{k:profile[k] for k in ['p50','p95','mean']}),ims,seq);seq+=1
  call('start',{});startwall=time.monotonic();nextissue=startwall
  while True:
   status=call('status');state=status.get('state',status.get('now',status));laststate=state
   if state.get('done') or state.get('race_over'):break
   if state.get('awaiting_review') or state.get('world')=='frozen' or state.get('phase')=='review':
    for f in pending.values():f.result()
    pending.clear();history.clear();plan.clear()
    call('ready',{'why':'Reviewed completed heat and current referee outcome.','plan':'Continue the frozen camera-driven policy.'})
    nextissue=time.monotonic();currentheat=None;continue
   now=time.monotonic()
   ready=[i for i,f in pending.items() if f.done()]
   if ready:
    results={i:pending.pop(i).result() for i in ready};chosen=max(ready)
    if chosen>last:
     last=chosen;commands,meta=results[chosen];plan=[];when=now
     for speed,steer,duration in commands:
      plan.append((when,{'type':'drive','speed':speed,'steering':steer},chosen));when+=duration*a.slowdown
   if plan and plan[0][0]<=now:
    _,cmd,ident=plan.pop(0);r=call('act',cmd);append(a.out/'applied.jsonl',{'seq':ident,'wall':now-startwall,'command':cmd,'took_effect':r.get('took_effect')});applied.append(ident)
   if now>=nextissue:
    nextissue=now+a.cadence*a.slowdown
    if len(pending)<a.capacity:
     v=call('observe',{});s=v['now']
     if s.get('done') or s.get('phase')=='review':continue
     image=base64.b64decode(v['observation']['image_png_b64'])
     if a.variant=='metric':s['camera_measurements']=camera_metrics(image,public_spec)
     history.append((s,image))
     prompt=prompt_for([x[0] for x in history],a.variant,a.chunk,{k:profile[k] for k in ['p50','p95','mean']})
     prompt+=f'\nReal API execution at 1/{a.slowdown:g} real speed. Pending answers are unknown.'
     write(a.out/f'decision_{seq:05d}'/'input.json',{'prompt':prompt})
     pending[seq]=pool.submit(infer,prompt,[x[1] for x in history],seq);seq+=1
   time.sleep(.1)
  for f in pending.values():f.result()
  svc=procs[1][0];os.kill(svc.pid,signal.SIGUSR1)
  for _ in range(240):
   final=json.loads((data/'final.json').read_text())
   if final.get('graded_ready'):break
   time.sleep(.25)
  else:raise RuntimeError('live service replay did not finalize')
  summary={'status':'complete','match_winner':final.get('match_winner'),'won':final.get('match_winner')=='A','valid_trial':final.get('valid_trial'),'deterministic':final.get('deterministic'),'sim_lag':final.get('sim_lag'),'slowdown':a.slowdown,'calls':seq,'applied_commands':len(applied),'wall_seconds':time.monotonic()-startwall,'model':MODEL,'service_tier':'ultrafast','artificial_delay':False,'harbor_isolation':False}
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
