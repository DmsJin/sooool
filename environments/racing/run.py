"""Camera-only GPT racing research. Secrets enter through process memory, never files.

The model never receives simulator state, seed, future delays or unarrived answers.
Local simulations are research evaluations, not Harbor official benchmark scores.
"""
import argparse, base64, collections, concurrent.futures as cf, fcntl
import hashlib, heapq, json, math, os, pathlib, queue, random, statistics
import subprocess, sys, threading, time, uuid, tempfile, shutil

if not os.environ.get('RACING_ENV_ROOT'):
 raise RuntimeError('Set RACING_ENV_ROOT to the read-only roboolympics environment checkout')
ROOT = pathlib.Path(os.environ['RACING_ENV_ROOT']).expanduser().resolve()
if not (ROOT/'core'/'episode.py').is_file():raise RuntimeError('RACING_ENV_ROOT is not a roboolympics checkout')
WORK_ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WORK_ROOT.parents[1]))
from runtime.options import credential
os.environ.setdefault('MUJOCO_GL', 'osmesa')
os.environ.setdefault('LP_NUM_THREADS', '1')
MODEL = 'gpt-6.1-sol'
MINIMAL_SYSTEM = 'Follow the latest user task policy and requested output exactly.\nUse brief reasoning sufficient for a correct decision.\nPreserve necessary checks, but avoid redundant verification,\nexhaustive alternatives, or expanding the task.\nReturn only the requested output, then stop.\nDo not force reasoning to zero.\n'
PROMPT = '''Win this RoboRacer match: finish a lap ahead of the opponent, and win two heats.
At Level 1 the scripted opponent cruises at 1.75 m/s. Safe but consistently slower driving loses.
Pass safely through the free lane when another car blocks you; do not just follow it indefinitely.
Drive from the attached car camera images, oldest to newest. Positive steering turns LEFT.
Yellow stripe is the track centre, green is road, magenta objects are fixed obstacles.
Keep inside red/white walls, pass obstacles through the open gap, avoid other cars.
Speed is [-1.5,4] m/s; steering [-0.48,0.48] radians. Commands hold until replaced.
Use the image sequence and own speed to anticipate where the car will be when the command arrives.
Do not repeat a correction already in progress. Brake before a tight bend, accelerate on straights.
Return ONLY a JSON array of [speed,steering,duration_game_seconds] commands, no explanation.
Each duration must be between 0.05 and 1.0. New arrived plans replace old remaining plans.
'''
VARIANTS = {
 'basic': 'Choose a short safe driving command from the newest image.',
 'anticipate': 'Estimate lateral motion from the image sequence. Countersteer early to avoid overshoot; account for delayed steering changes.',
 'smooth': 'Use moderate steering, speed 2.2-3.4 on straights, brake to 1.2-2.0 for bends. Avoid oscillation and use a far lookahead.',
 'chunk': 'Plan successive commands over the coming interval, braking before turns and then straightening. Replan on fresh images.',
 'recover': 'If speed stays low despite forward commands and a wall fills the image, briefly reverse with steering to free the car, then rejoin the road.'
}
VARIANTS['metric']='Use the camera-derived ground points as measurements, and still inspect the images. Car coordinates are x=forward metres, y=left metres. Choose a reachable safe lookahead target, predict motion during the median-to-P95 delay, and steer toward the target from that predicted frame. The wheelbase is 0.46 m: steering to a point (x,y) can be estimated as atan(0.92*y/(x*x+y*y)), clipped to the action range. Small steering of 0.1 rad gives a radius about 4.6 m, so sharp bends require more steering or lower speed. Prefer 2.5-3.6 m/s on clear straights. Brake before a tight bend or a nearby obstacle. If commanded forward but stuck, reverse to free the car. These are noisy image measurements, not world state.'

def camera_metrics(image,spec):
 import io,numpy as np
 from PIL import Image
 im=np.asarray(Image.open(io.BytesIO(image)))[:,:,:3].astype(float)
 h,w=im.shape[:2];cam=spec['camera'];front=cam['front'];f=h/(2*math.tan(math.radians(cam['fovy_deg'])/2));pitch=math.radians(front['pitch_down_deg'])
 v,u=np.mgrid[:h,:w];vy=(h/2-v)/f;dz=-math.sin(pitch)+vy*math.cos(pitch)
 scale=-front['height_m']/np.minimum(dz,-.001);gx=front['offset_m']+scale*(math.cos(pitch)+vy*math.sin(pitch));gy=-scale*(u-w/2)/f
 r,g,b=im[:,:,0],im[:,:,1],im[:,:,2];valid=(dz<-.03)&(gx>.3)&(gx<6)
 yellow=(r>140)&(g>110)&(g>.65*r)&(b<100)&valid
 xs,ys=gx[yellow],gy[yellow];out={'stripe_pixels':len(xs),'frame':'car x forward m, y left m'}
 if len(xs)>=10:
  coef=np.polynomial.polynomial.polyfit(xs,ys,2);res=np.abs(np.polynomial.polynomial.polyval(xs,coef)-ys)
  keep=res<max(.12,float(np.quantile(res,.8)))
  if keep.sum()>=10:coef=np.polynomial.polynomial.polyfit(xs[keep],ys[keep],2)
  out.update(ground_path=[[x,round(float(np.polynomial.polynomial.polyval(x,coef)),3)] for x in [.5,1,1.5,2,3,4,5] if xs.min()<=x<=xs.max()],fit_rms_m=round(float(np.sqrt(np.mean(res**2))),3))
 magenta=(r>140)&(b>100)&(g<90)&valid
 edge=magenta & ~np.vstack([magenta[1:],np.zeros((1,w),dtype=bool)])
 if edge.any():out['magenta_ground_bounds']={'x_near':round(float(gx[edge].min()),3),'x_far':round(float(gx[edge].max()),3),'y_min':round(float(gy[edge].min()),3),'y_max':round(float(gy[edge].max()),3)}
 return out

def write(path, value):
 path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
 tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(value,indent=2)); tmp.replace(path)

def append(path, value):
 with pathlib.Path(path).open('a') as f: f.write(json.dumps(value)+'\n'); f.flush()

def parse(answer, size=1):
 s=answer.strip(); s=s.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
 a=json.loads(s)
 if not isinstance(a,list) or len(a)!=size: raise ValueError('wrong command count')
 out=[]
 for c in a:
  if not isinstance(c,list) or len(c)!=3: raise ValueError('wrong command shape')
  v,d,t=map(float,c)
  if not all(map(math.isfinite,(v,d,t))) or not (-1.5<=v<=4 and -.48<=d<=.48 and .05<=t<=1):raise ValueError('invalid command values')
  out.append([round(v,6),round(d,6),round(t,6)])
 return out

class Budget:
 def __init__(self,path,cache_aware=False):
  self.path=pathlib.Path(path);self.lock=self.path.with_suffix('.lock');self.cache_aware=cache_aware
  self.price_caps={'input':16.5,'cached_input':.66,'output':66} if cache_aware else {'input':15,'cached_input':15,'output':60}
 def update(self,fn):
  self.path.parent.mkdir(parents=True,exist_ok=True)
  with self.lock.open('a') as f:
   fcntl.flock(f,fcntl.LOCK_EX)
   d=json.loads(self.path.read_text()) if self.path.exists() else {'limit_usd':30,'charged_upper_usd':0,'reserved':{},'stages':{}}
   result=fn(d);write(self.path,d);return result
 def reserve(self,prompt,images,stage,cap,additional_input_tokens=0):
  # Deliberately conservative: 16k tokens per 240x160 image, every UTF-8 byte
  # charged as a token at cache-write price, and full 512-token output allowance.
  if not isinstance(additional_input_tokens,int) or additional_input_tokens<0:raise ValueError('context token bound')
  bound=len(prompt.encode())+16384*len(images)+additional_input_tokens
  if self.cache_aware and bound>272000:raise RuntimeError('short-context pricing bound exceeded')
  upper=(bound*self.price_caps['input']+512*self.price_caps['output'])/1e6
  rid=uuid.uuid4().hex
  def fn(d):
   all_reserved=sum(v['usd'] for v in d['reserved'].values())
   stage_reserved=sum(v['usd'] for v in d['reserved'].values() if v['stage']==stage)
   if d['charged_upper_usd']+all_reserved+upper>d['limit_usd'] or d['stages'].get(stage,0)+stage_reserved+upper>cap:raise RuntimeError('budget admission stopped')
   d['reserved'][rid]={'usd':upper,'stage':stage}
   if self.cache_aware:d['reserved'][rid]['price_caps']=dict(self.price_caps)
   return rid
  return self.update(fn)
 def settle(self,rid,usage):
  def fn(d):
   r=d['reserved'].pop(rid)
   if usage is None:cost=r['usd'] # Uncertain requests retain their full reservation as spent.
   else:
    caps=r.get('price_caps',{'input':15,'cached_input':15,'output':60});cached=(usage.get('input_tokens_details') or {}).get('cached_tokens',0)
    if type(cached) is not int or not 0<=cached<=usage['input_tokens']:cached=0
    cost=((usage['input_tokens']-cached)*caps['input']+cached*caps['cached_input']+usage['output_tokens']*caps['output'])/1e6
   if cost>r['usd']:raise RuntimeError('token bound exceeded; stop all paid calls')
   d['charged_upper_usd']+=cost;d['stages'][r['stage']]=d['stages'].get(r['stage'],0)+cost
   return cost
  return self.update(fn)

class API:
 def __init__(self,key,budget,stage='profile',cap=6,endpoint='https://api.openai.com/v1/responses',instructions=None,image_detail='low',stateful=False):
  import requests
  self.key=key;self.http=requests.Session();self.budget=budget;self.stage=stage;self.cap=cap;self.endpoint=endpoint
  self.instructions=instructions;self.image_detail=image_detail;self.stateful=stateful;self.history=[];self.previous_input_upper=0;self.completed_turns=0;self.state_lock=threading.Lock()
 def act(self,prompt,images,directory,on_ready=None,validator=None):
  if self.stateful and not self.state_lock.acquire(blocking=False):raise RuntimeError('overlapping stateful API requests forbidden')
  try:return self._act(prompt,images,directory,on_ready,validator)
  finally:
   if self.stateful:self.state_lock.release()
 def _act(self,prompt,images,directory,on_ready=None,validator=None):
  directory=pathlib.Path(directory);directory.mkdir(parents=True,exist_ok=True)
  write(directory/'input.json',{'prompt':prompt,'instructions':self.instructions,'image_sha256':[hashlib.sha256(x).hexdigest() for x in images],'model':MODEL,'effort':'low','service_tier':'ultrafast','image_detail':self.image_detail,'stateful':self.stateful,'prior_completed_turns':self.completed_turns})
  for i,im in enumerate(images):(directory/f'image_{i}.png').write_bytes(im)
  rid=self.budget.reserve((self.instructions or '')+prompt,images,self.stage,self.cap,additional_input_tokens=self.previous_input_upper if self.stateful else 0)
  content=[{'type':'input_text','text':prompt}]+[{'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(x).decode(),'detail':self.image_detail} for x in images]
  payload={'model':MODEL,'service_tier':'ultrafast','reasoning':{'effort':'low'},'text':{'verbosity':'low'},'max_output_tokens':512,'stream':True,'store':False,'prompt_cache_key':'racing-autoresearch-v1','input':[{'role':'user','content':content}]}
  if self.stateful:
   payload['input']=self.history+payload['input'];payload['include']=['reasoning.encrypted_content']
  if self.instructions is not None:payload['instructions']=self.instructions
  started=time.perf_counter();first=None;response=None;usage=None
  streamed="";published=None;json_ready=None;completed=None;identity=None;candidate=None
  try:
   with self.http.post(self.endpoint,headers={'Authorization':'Bearer '+self.key},json=payload,stream=True,timeout=(10,60)) as r:
    if r.status_code!=200:
     try:e=r.json().get('error',{});desc=str(e.get('code') or e.get('type') or 'request_error')
     except Exception:desc='request_error'
     raise RuntimeError(f'API HTTP {r.status_code}: {desc}')
    for line in r.iter_lines(chunk_size=1):
     if not line.startswith(b'data: ') or line[6:]==b'[DONE]':continue
     e=json.loads(line[6:])
     kind=e.get('type')
     if kind in ('response.created','response.in_progress'):
      identity=e.get('response',{})
     if kind=='response.output_text.delta':
      if first is None:first=time.perf_counter()-started
      streamed+=e.get('delta','')
      if validator is not None and candidate is None:
       try:
        # Strict complete JSON first: never accept a partial numeric token,
        # incomplete row, repaired JSON or a fenced prefix as an action.
        json.loads(streamed);candidate=validator(streamed)
       except (ValueError,TypeError,OverflowError):pass
       else:json_ready=time.perf_counter()-started
     if kind in ('response.completed','response.incomplete','response.failed'):
      response=e['response'];usage=response.get('usage');completed=time.perf_counter()-started
      identity=response
     if on_ready is not None and candidate is not None and published is None:
      # Do not publish before the actual returned identity is known. Some
      # backends omit tier until completed; those safely fall back to that event.
      if identity and identity.get('model')==MODEL and identity.get('service_tier')=='ultrafast':
       published=time.perf_counter()-started
       on_ready(candidate,{'json_ready_seconds':json_ready,'published_seconds':published,'model':MODEL,'service_tier':'ultrafast','invalid_output':False})
   stream_end=time.perf_counter()-started
   if not response or response.get('status')!='completed':raise RuntimeError('API did not complete')
   if response.get('service_tier')!='ultrafast' or response.get('model')!=MODEL:raise RuntimeError('API model/tier mismatch')
   answer=''.join(c.get('text','') for i in response['output'] if i['type']=='message' for c in i['content'] if c['type']=='output_text')
   if published is not None:
    try:consistent=streamed.strip()==answer.strip() and validator(answer)==candidate
    except (ValueError,TypeError,OverflowError):consistent=False
    if not consistent:raise RuntimeError('API changed the published action after JSON closure')
   meta={'json_ready_seconds':json_ready,'published_seconds':published,'response_completed_seconds':completed,'stream_end_seconds':stream_end,'wall_seconds':stream_end,'ttft_seconds':first,'usage':usage,'model':response['model'],'service_tier':response['service_tier']}
   if self.stateful:
    if usage is None:raise RuntimeError('stateful API requires usage to bound subsequent context')
    self.history.append({'role':'user','content':content});self.history.extend(response['output']);self.previous_input_upper=usage['input_tokens']+usage['output_tokens']+4096;self.completed_turns+=1
    meta.update(stateful=True,session_turn=self.completed_turns,context_input_tokens=usage['input_tokens'])
   write(directory/'result.json',{'answer':answer,**meta});return answer,meta
  finally:
   cost=self.budget.settle(rid,usage)
   if 'meta' in locals():
    meta.update(charged_upper_usd=cost,price_caps=dict(self.budget.price_caps));write(directory/'result.json',{'answer':answer,**meta})
 def close(self):self.http.close();self.key=None;self.history.clear()

class Native:
 def __init__(self,directory,outer='minimal'):
  self.directory=pathlib.Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
  self.outer=outer;self.auth_home=None
  self.workspace=pathlib.Path(tempfile.mkdtemp(prefix='racing-native-'))
  env=dict(os.environ)
  for k in ['OPENAI_API_KEY','CODEX_API_KEY','CODEX_ACCESS_TOKEN']:env.pop(k,None)
  binary=os.environ.get('RACING_CODEX_BINARY') or shutil.which('codex')
  if not binary:raise RuntimeError('Set RACING_CODEX_BINARY to the authenticated subscription Codex executable')
  cmd=[binary,'-c','forced_login_method="chatgpt"','-c','model_provider="research_subscription"','-c','model_providers.research_subscription.name="Subscription SSE"','-c','model_providers.research_subscription.requires_openai_auth=true','-c','model_providers.research_subscription.supports_websockets=false','-c','model_providers.research_subscription.wire_api="responses"','-c','service_tier="ultrafast"','-c','features.apps=false','-c','features.plugins=false','-c','memories.use_memories=false','-c','project_doc_max_bytes=0','-c','features.shell_tool=false','-c','tools.view_image=false','-c','web_search="disabled"','-c','history.persistence="none"','app-server']
  if outer=='minimal':
   # Legacy tools.view_image is silently ignored without strict mode in 0.162.1.
   # The supported features.view_image switch is set in the isolated config.
   bad=cmd.index('tools.view_image=false');del cmd[bad-1:bad+1]
   # Isolate global AGENTS/config. Only the existing subscription login is copied;
   # no paid API credential enters this temporary home, which close() removes.
   source_home=pathlib.Path(env.get('CODEX_HOME',str(pathlib.Path.home()/'.codex')))
   self.auth_home=pathlib.Path(tempfile.mkdtemp(prefix='racing-auth-'))
   self.auth_home.chmod(0o700)
   shutil.copyfile(source_home/'auth.json',self.auth_home/'auth.json')
   (self.auth_home/'auth.json').chmod(0o600);env['CODEX_HOME']=str(self.auth_home)
   system=self.auth_home/'system.txt'
   system.write_text(MINIMAL_SYSTEM)
   (self.auth_home/'config.toml').write_text('developer_instructions = ""\nproject_doc_max_bytes = 0\ninclude_apps_instructions = false\ninclude_collaboration_mode_instructions = false\ninclude_environment_context = false\ninclude_permissions_instructions = false\n[skills]\ninclude_instructions = false\n[memories]\nuse_memories = false\n[features]\napps = false\nplugins = false\nmulti_agent = false\nshell_tool = false\nview_image = false\nskill_search = false\ncomputer_use = false\nbrowser_use = false\nworkspace_dependencies = false\nsleep_tool = false\n')
   cmd[1:1]=['--strict-config','-c','model_instructions_file='+json.dumps(str(system))]
  elif outer!='current':raise ValueError('unknown native outer')
  self.err=(self.directory/'native.stderr').open('w')
  self.p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,text=True,env=env,cwd=self.workspace)
  self.q=queue.Queue();self.events=collections.deque();self.seq=0
  def reader():
   for line in self.p.stdout:
    try:
     event=json.loads(line);event['_received_perf_counter']=time.perf_counter();self.q.put(event)
    except ValueError:pass
   self.q.put({'fatal_eof':True})
  threading.Thread(target=reader,daemon=True).start()
  try:
   self.rpc('initialize',{'clientInfo':{'name':'racing-research','version':'1.0'},'capabilities':{'experimentalApi':True}})
   self.send({'method':'initialized'})
   acc=self.rpc('account/read',{'refreshToken':False})
   if (acc.get('account') or {}).get('type')!='chatgpt':raise RuntimeError('subscription login required; no API fallback')
  except BaseException:
   self.close();raise
 def send(self,msg):self.p.stdin.write(json.dumps(msg)+'\n');self.p.stdin.flush()
 def rpc(self,method,params):
  self.seq+=1;ident=self.seq;self.send({'id':ident,'method':method,'params':params});end=time.monotonic()+150
  while time.monotonic()<end:
   e=self.q.get(timeout=150)
   if e.get('fatal_eof'):raise RuntimeError('Native server exited; see native.stderr')
   if e.get('id')==ident:
    if 'error' in e:raise RuntimeError('Native RPC '+method+': '+json.dumps(e['error']))
    return e.get('result',{})
   # Notifications can arrive before the RPC reply. Dropping a completion here
   # leaves act() waiting for an event that already happened, until its timeout.
   if e.get('method'):self.events.append(e)
  raise TimeoutError(method)
 def act(self,prompt,images,directory,validator=None):
  total_started=time.perf_counter()
  directory=pathlib.Path(directory);directory.mkdir(parents=True,exist_ok=True)
  limits=self.rpc('account/rateLimits/read',{})
  # Never buy extra credits or fall back to paid API when subscription is exhausted.
  def exhausted(d):
   if isinstance(d,dict):return d.get('usedPercent',0)>=99 or any(exhausted(v) for v in d.values())
   if isinstance(d,list):return any(exhausted(v) for v in d)
   return False
  if exhausted(limits):raise RuntimeError('subscription quota exhausted')
  setup={'model':MODEL,'cwd':str(self.workspace),'approvalPolicy':'never','sandbox':'read-only','ephemeral':True,'developerInstructions':''}
  if self.outer=='current':setup['baseInstructions']='You are a realtime racing controller. Use only the provided images and legal telemetry. Return only the requested JSON commands. Do not use tools.'
  thread=self.rpc('thread/start',setup)['thread']['id']
  inputs=[{'type':'text','text':prompt}]
  for i,b in enumerate(images):
   p=directory/f'image_{i}.png';p.write_bytes(b)
   opaque=self.workspace/f'image_{i}.png';opaque.write_bytes(b);inputs.append({'type':'localImage','path':str(opaque),'detail':'auto'})
  started=time.perf_counter();r=self.rpc('turn/start',{'threadId':thread,'input':inputs,'effort':'low','serviceTier':'ultrafast','approvalPolicy':'never'});turn=r['turn']['id'];texts=[];partial='';first_delta=None;syntax_ready=None;valid_ready=None;candidate=None;message_done=None
  usage=None
  while True:
   e=self.events.popleft() if self.events else self.q.get(timeout=150);p=e.get('params',{})
   if p.get('threadId')!=thread or p.get('turnId') not in (None,turn):continue
   elapsed=e.get('_received_perf_counter',time.perf_counter())-started
   if e.get('method')=='item/agentMessage/delta':
    if first_delta is None:first_delta=elapsed
    partial+=p.get('delta','')
    try:json.loads(partial)
    except (ValueError,TypeError):pass
    else:
     if syntax_ready is None:syntax_ready=elapsed
     if validator is not None and valid_ready is None:
      try:candidate=validator(partial)
      except (ValueError,TypeError,OverflowError):pass
      else:valid_ready=elapsed
   if e.get('method')=='model/rerouted' and p.get('toModel')!=MODEL:raise RuntimeError('subscription model was rerouted; trial rejected')
   if e.get('method')=='thread/tokenUsage/updated':usage=p.get('tokenUsage')
   if e.get('method')=='item/completed':
    kind=p.get('item',{}).get('type')
    if kind=='agentMessage':texts.append(p['item'].get('text',''));message_done=elapsed
    elif kind not in ('reasoning','userMessage'):raise RuntimeError('Policy attempted a tool; result rejected: '+str(kind))
   if e.get('method')=='turn/completed' and p.get('turn',{}).get('id')==turn:
    if p['turn'].get('status')!='completed':raise RuntimeError('native turn failed')
    break
  answer='\n'.join(texts);meta={'wall_seconds':time.perf_counter()-started,'first_delta_seconds':first_delta,'syntax_json_ready_seconds':syntax_ready,'valid_json_ready_seconds':valid_ready,'agent_message_completed_seconds':message_done,'auth':'chatgpt','native_outer':self.outer,'model_requested':MODEL,'reasoning_requested':'low','service_tier_requested':'ultrafast','subscription_tier_verified':False,'image_input_detail':'auto','api_cost_usd':0,'token_usage':usage}
  write(directory/'result.json',{'answer':answer,**meta})
  unsubscribe_started=time.perf_counter()
  self.rpc('thread/unsubscribe',{'threadId':thread})
  meta.update(full_wall_seconds=time.perf_counter()-total_started,setup_wall_seconds=started-total_started,unsubscribe_seconds=time.perf_counter()-unsubscribe_started)
  write(directory/'result.json',{'answer':answer,**meta})
  return answer,meta
 def close(self):
  self.p.terminate()
  try:self.p.wait(timeout=10)
  except subprocess.TimeoutExpired:self.p.kill();self.p.wait()
  self.err.close();shutil.rmtree(self.workspace)
  if self.auth_home:shutil.rmtree(self.auth_home)

def make_world(seed,level,slowdown):
 from core.episode import load_plugin
 from core.local import Views,seat_spec
 from core.sport import MatchConfig
 import core.spec as sm
 plugin=str(ROOT/'sports/racing/plugin.py');sport=load_plugin(plugin)
 cfg=MatchConfig(sport='racing',format='match',seats=('A',),seed=seed,first='A',slowdown=slowdown,level=level,action_level='low')
 m=sport.build(cfg);views=Views(sport,cfg,m,sm.load(plugin),True,plugin)
 return sport,cfg,m,views,seat_spec(sport,cfg,'A',m,plugin)

def observe(m,views):
 v=views.view('A',{'step':m.k,'t_sim':round(m.k*m.dt,4),'phase':'running','done':False})
 image=base64.b64decode(v['observation']['image_png_b64'])
 return v['state'],image

def preflight(out):
 from core.episode import Episode
 from core.sport import FINISHED,UNIT_OVER
 sport,cfg,m,views,spec=make_world(101,1,1)
 ep=Episode(out/'episode.jsonl');ep.write('header',cfg=cfg.to_json(),sport=sport.name,revision=sport.revision,protocol='realtime',source_sha=None)
 write(out/'spec.json',spec)
 sys.path.insert(0,str(ROOT/'sports/racing'))
 from builtin_players import Reference
 ref=Reference(spec,'A',101)
 samples=[]
 while m.phase().state!=FINISHED:
  if m.phase().state==UNIT_OVER:ep.write('resume',k=m.k);m.resume()
  if m.k%10==0:
   state,image=observe(m,views);v={'state':state,'observation':{'image_png_b64':base64.b64encode(image).decode()}}
   cmd=ref.act(v);ep.write('cmd',k=m.k,seat='A',cmd=cmd);m.apply('A',cmd)
   if len(samples)<32 and m.k%70==0:
    p=out/f'sample_{len(samples):03d}.png';p.write_bytes(image);samples.append({'image':p.name,'state':state})
  m.step()
 ep.write('end',k=m.k,reason='match_over')
 write(out/'samples.json',samples)
 result={'phase':m.phase().state,'scores':m.scores(),'digest':m.state_digest(),'steps':m.k,'samples':len(samples),'api_cost_usd':0}
 write(out/'summary.json',result);print(json.dumps(result),flush=True)
 r=subprocess.run([sys.executable,'-m','core.episode',str(ROOT/'sports/racing/plugin.py'),str(out)],cwd=ROOT,capture_output=True,text=True)
 print(r.stdout[-1500:]);print(r.stderr[-1500:])
 if r.returncode:raise RuntimeError('replay failed')
 replay=json.loads((out/'replay_check.json').read_text())
 if replay.get('state_sha')!=result['digest']:raise RuntimeError('replay digest mismatch')

def prompt_for(states,variant,chunk,delays):
 return PROMPT+'\n'+VARIANTS[variant]+f'\nReturn exactly {chunk} command(s). Measured API complete-response delay seconds: '+json.dumps(delays)+'.\nVisible observations: '+json.dumps(states,separators=(',',':'))

def controller_prompt(states,variant,chunk,delays,slowdown,control='servo',anchor='arrival',remaining_points=None):
 """One frozen task template for subscription simulation and live API execution."""
 prompt=prompt_for(states,variant,chunk,delays)
 prompt+=f'\nThis episode runs at 1/{slowdown:g} real speed; delays above are real seconds, divide by {slowdown:g} for game seconds. Pending answers are unknown.'
 if control=='waypoint':
  from waypoints import PROMPT as WAYPOINT_PROMPT
  prompt=WAYPOINT_PROMPT+'\nMeasured complete API delay real seconds: '+json.dumps(delays)+f'. Slowdown {slowdown:g}; divide real delay by slowdown for game delay.\nVisible observations: '+json.dumps(states,separators=(',',':'))+'\nEarlier arrived plan, estimated relative to the current car: '+json.dumps(remaining_points or [])
 if control=='lane':
  from lane import PROMPT as LANE_PROMPT
  prompt=LANE_PROMPT+'\nMeasured API delay real seconds: '+json.dumps(delays)+f'. Slowdown {slowdown:g}.\nVisible observations: '+json.dumps(states,separators=(',',':'))
 if control not in ('waypoint','lane') and anchor=='issue':prompt+='\nYour three commands are a time-anchored plan starting at the observation time, NOT when the response arrives. Each command must last exactly 1.0 game second, covering now, +1s and +2s. Predict the trajectory over that interval. The executor skips already elapsed commands, applies the currently due command on arrival, and brakes if the entire plan is too old.'
 return prompt

def profile(args,key):
 samples=json.loads((args.samples/'samples.json').read_text());rows=[]
 client=API(key,Budget(args.budget))
 try:
  for i in range(args.calls):
   s=samples[i%len(samples)];ims=[(args.samples/s['image']).read_bytes()]
   prompt=prompt_for([s['state']],'basic',1,{'unknown':True})
   answer,meta=client.act(prompt,ims,args.out/f'call_{i:03d}');cmd=parse(answer)
   row={'index':i,'commands':cmd,**meta};rows.append(row);append(args.out/'measurements.jsonl',row)
   print('PROFILE '+json.dumps({'index':i,'seconds':meta['wall_seconds'],'ttft':meta['ttft_seconds'],'input_tokens':meta['usage']['input_tokens'],'output_tokens':meta['usage']['output_tokens']}),flush=True)
 finally:client.close()
 values=sorted(x['wall_seconds'] for x in rows)
 summary={'n':len(rows),'concurrency':1,'min':min(values),'p50':statistics.median(values),'p95':values[min(len(values)-1,math.ceil(len(values)*.95)-1)],'mean':statistics.mean(values),'delays':values,'model':MODEL,'service_tier':'ultrafast','effort':'low','image_count':1}
 write(args.out/'profile.json',summary);print('PROFILE_DONE '+json.dumps(summary),flush=True)

def schedule_commands(commands,issued,arrived,dt,anchor):
 cursor=issued if anchor=='issue' else arrived
 timeline=[]
 for speed,steer,duration in commands:
  timeline.append((cursor,{'type':'drive','speed':speed,'steering':steer}))
  cursor+=max(1,round(duration/dt))
 if anchor=='issue' and arrived>=cursor:return [(arrived,{'type':'none'})]
 current=[x for x in timeline if x[0]<=arrived]
 return ([(arrived,current[-1][1])] if current else [])+[x for x in timeline if x[0]>arrived]


def simulate(args):
 from core.episode import Episode
 from core.sport import FINISHED,UNIT_OVER,parse_action
 from core.outcome import decide
 profile=json.loads(args.profile.read_text());delays=profile['delays']
 sport,cfg,m,views,spec=make_world(args.seed,args.level,args.slowdown)
 from waypoints import Ego,Tracker,parse_points
 from lane import Lane,parse_lane
 ego=Ego();tracker=Lane() if args.control=='lane' else Tracker(ego);origins={};odo_step=m.k;crash_count=0;invalid_before=-1
 ep=Episode(args.out/'episode.jsonl');ep.write('header',cfg=cfg.to_json(),sport=sport.name,revision=sport.revision,protocol='realtime',source_sha=None)
 config={k:str(v) if isinstance(v,pathlib.Path) else v for k,v in vars(args).items()}
 config.update(auth='camera-waypoint-reference-NOT-GPT' if args.reference_waypoints else 'chatgpt',native_outer=None if args.reference_waypoints else 'minimal',future_results_visible=False,api_cost_usd=0)
 write(args.out/'config.json',config)
 (args.out/'runner_snapshot.py').write_bytes(pathlib.Path(__file__).read_bytes())
 (args.out/'waypoints_snapshot.py').write_bytes(pathlib.Path(__file__).with_name('waypoints.py').read_bytes())
 (args.out/'lane_snapshot.py').write_bytes(pathlib.Path(__file__).with_name('lane.py').read_bytes())
 clients=[];local=threading.local();lock=threading.Lock()
 def act(prompt,images,ident):
  write(args.out/f'decision_{ident:05d}'/'input.json',{'prompt':prompt,'image_sha256':[hashlib.sha256(x).hexdigest() for x in images]})
  if args.reference_waypoints:
   visible,_=json.JSONDecoder().raw_decode(prompt.split('Visible observations: ',1)[1]);state=visible[-1];metrics=state.get('camera_measurements',{});path=metrics.get('ground_path',[])
   lane=.38 if state['own']['grid_side']=='inner' else -.38
   obstacle=metrics.get('magenta_ground_bounds')
   if obstacle and obstacle['x_near']<4:lane=-.8 if (obstacle['y_min']+obstacle['y_max'])/2>0 else .8
   points=[]
   for x in [2,4,5]:
    if path:px,py=min(path,key=lambda p:abs(p[0]-x));points.append([px,py+lane,3.0])
    else:points.append([-1,.3,-.6])
   result={'commands':points,'auth':'camera-reference-NOT-GPT','wall_seconds':0};write(args.out/f'decision_{ident:05d}'/'result.json',{'answer':json.dumps(points),**result});return result
  if not hasattr(local,'client'):
   with lock:target=args.out/f'worker_{len(clients)}';client=Native(target);clients.append(client)
   local.client=client
  answer,meta=local.client.act(prompt,images,args.out/f'decision_{ident:05d}')
  try:commands=parse_lane(answer,args.chunk) if args.control=='lane' else parse_points(answer,args.chunk) if args.control=='waypoint' else parse(answer,args.chunk)
  except (ValueError,TypeError) as e:
   # Invalid model output is an observed policy error, not an edited action.
   # Brake on its scheduled arrival, then await the next actual GPT decision.
   write(args.out/f'decision_{ident:05d}'/'rejection.json',{'error':str(e),'fallback':'brake until next valid GPT plan'})
   return {'commands':[],'invalid_output':True,**meta}
  return {'commands':commands,'invalid_output':False,**meta}
 pool=cf.ThreadPoolExecutor(max_workers=args.workers)
 rng=random.Random(args.seed+7000);pending=[];plan=[];seq=0;last=-1;next_issue=0;drops=0;peak=0
 prior=[]
 if args.resume_from:
  prior=[json.loads(x) for x in (args.resume_from/'issued.jsonl').read_text().splitlines()]
  cutoff=0
  while cutoff<len(prior) and (args.resume_from/f'decision_{cutoff:05d}'/'result.json').exists():cutoff+=1
  prior=prior[:cutoff]
 stride=max(1,round(args.cadence/m.dt));started=time.monotonic();history=collections.deque(maxlen=args.history)
 summary={'status':'incomplete','api_cost_usd':0,'auth':config['auth'],'control':args.control,'seed':args.seed,'level':args.level,'slowdown':args.slowdown};age=[]
 try:
  while m.phase().state!=FINISHED:
   if m.phase().state==UNIT_OVER:
    # Drain results belonging to the completed heat. They can never affect a new heat.
    for _,_,_,f in pending:f.result()
    pending.clear();plan.clear();history.clear();ep.write('resume',k=m.k);m.resume();next_issue=m.k;ego=Ego();tracker=Lane() if args.control=='lane' else Tracker(ego);odo_step=m.k;crash_count=0;invalid_before=m.k
   if args.control in ('waypoint','lane') and m.k%(20 if args.control=='lane' else 10)==0:
    public=m.observe('A');own=public['own'];ego.update(own['forward_speed'],own['command'][1],(m.k-odo_step)*m.dt);odo_step=m.k
    if len(public['crashes_this_heat'])>crash_count:tracker.clear();invalid_before=m.k
    crash_count=len(public['crashes_this_heat'])
   ready=[]
   while pending and pending[0][0]<=m.k:ready.append(heapq.heappop(pending))
   if ready:
    due,ident,seen,f=max(ready,key=lambda x:x[1])
    results={x[1]:x[3].result() for x in ready}
    for x in ready:append(args.out/'arrivals.jsonl',{'seq':x[1],'due_step':x[0],'seen_step':x[2],**results[x[1]]})
    if ident>last:
     last=ident
     if results[ident].get('invalid_output'):
      tracker.clear();tracker.seq=ident;tracker.seen=seen
      plan=[(m.k,{'type':'none'},ident,seen)]
     elif args.control in ('waypoint','lane'):
      if seen>=invalid_before:tracker.offer(results[ident]['commands'],origins[ident],seen*m.dt,ident,seen)
     else:plan=[(when,cmd,ident,seen) for when,cmd in schedule_commands(results[ident]['commands'],seen,m.k,m.dt,args.anchor)]
   if args.control in ('waypoint','lane') and m.k%(20 if args.control=='lane' else 10)==0:
    own=m.observe('A')['own']
    if args.control=='lane':
     _,fresh_image=observe(m,views);cmd=tracker.drive(m.k*m.dt,camera_metrics(fresh_image,spec))
    else:cmd=tracker.drive(m.k*m.dt,own['forward_speed'])
    cmd=parse_action(sport.action_layer('low'),'A',cmd,m,{})
    ep.write('cmd',k=m.k,seat='A',cmd=cmd,seen=tracker.seen if tracker.seen>=0 else m.k);m.apply('A',cmd)
    append(args.out/'waypoint_actions.jsonl',{'k':m.k,'model_seq':tracker.seq,'seen':tracker.seen,'estimated_ego':ego.pose(),'remaining_destinations':tracker.local_points(),'applied_command':cmd})
    if tracker.seen>=0:age.append((m.k-tracker.seen)*m.dt)
   while plan and plan[0][0]<=m.k:
    _,cmd,ident,seen=plan.pop(0);cmd=parse_action(sport.action_layer('low'),'A',cmd,m,{})
    ep.write('cmd',k=m.k,seat='A',cmd=cmd,seen=seen);m.apply('A',cmd);age.append((m.k-seen)*m.dt)
   if m.k>=next_issue:
    next_issue=m.k+stride
    if len(pending)>=args.capacity:drops+=1
    else:
     state,image=observe(m,views);history.append((state,image))
     if args.variant=='metric':state['camera_measurements']=camera_metrics(image,spec)
     prompt=controller_prompt([x[0] for x in history],args.variant,args.chunk,{k:profile[k] for k in ['p50','p95','mean']},args.slowdown,args.control,args.anchor,tracker.local_points())
     delay=rng.choice(delays);due=m.k+max(1,math.ceil(delay/args.slowdown/m.dt))
     hashes=[hashlib.sha256(x[1]).hexdigest() for x in history]
     saved=args.resume_from/f'decision_{seq:05d}'/'result.json' if args.resume_from and seq<len(prior) else None
     if saved and saved.exists():
      old=prior[seq]
      if (old['seen_step'],old['due_step'],old['image_sha256'])!=(m.k,due,hashes):raise RuntimeError('resume image/time prefix mismatch')
      prev=json.loads(saved.read_text());f=cf.Future();f.set_result({'commands':parse_lane(prev['answer'],args.chunk) if args.control=='lane' else parse_points(prev['answer'],args.chunk) if args.control=='waypoint' else parse(prev['answer'],args.chunk),'verified_prefix_replay':True})
      target=args.out/f'decision_{seq:05d}';target.mkdir();write(target/'result.json',prev)
     else:f=pool.submit(act,prompt,[x[1] for x in history],seq)
     origins[seq]=ego.pose()
     heapq.heappush(pending,(due,seq,m.k,f));peak=max(peak,len(pending))
     append(args.out/'issued.jsonl',{'seq':seq,'seen_step':m.k,'due_step':due,'delay_real_s':delay,'image_sha256':hashes})
     seq+=1
     if seq%25==0:print('SIM_PROGRESS '+json.dumps({'seed':args.seed,'variant':args.variant,'slowdown':args.slowdown,'calls':seq,'game_seconds':m.k*m.dt,'scores':m.scores(),'wall_seconds':time.monotonic()-started}),flush=True)
   m.step()
  ep.write('end',k=m.k,reason='match_over')
  for _,_,_,f in pending:f.result()
  outcome=decide(m,sides=['A','opponent'])
  summary.update(status='complete',winner=outcome.winner,won=outcome.winner=='A',scores=m.scores(),steps=m.k,digest=m.state_digest(),game_seconds=m.k*m.dt,calls=seq,drops=drops,invalid_output_count=len(list(args.out.glob('decision_*/rejection.json'))),peak_virtual_inflight=peak,mean_action_age_game_s=statistics.mean(age) if age else None,wall_seconds=time.monotonic()-started,heat_results=m.observe('A')['results'])
  r=subprocess.run([sys.executable,'-m','core.episode',str(ROOT/'sports/racing/plugin.py'),str(args.out)],cwd=ROOT,capture_output=True,text=True)
  if r.returncode:raise RuntimeError('simulation replay failed: '+r.stderr[-500:])
  replay=json.loads((args.out/'replay_check.json').read_text())
  summary['replay_matches']=replay['state_sha']==summary['digest']
  if not summary['replay_matches']:raise RuntimeError('simulation replay digest mismatch')
 except BaseException as e:
  summary.update(status='incomplete',error=type(e).__name__+': '+str(e),calls=seq,steps=m.k)
  raise
 finally:
  write(args.out/'summary.json',summary)
  pool.shutdown(wait=True,cancel_futures=True)
  for c in clients:c.close()
 print('SIM_DONE '+json.dumps(summary),flush=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['preflight','profile','native-probe','sim']);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--samples',type=pathlib.Path);p.add_argument('--budget',type=pathlib.Path,default=WORK_ROOT/'research-results/budget.json');p.add_argument('--calls',type=int,default=32)
 p.add_argument('--profile',type=pathlib.Path);p.add_argument('--seed',type=int,default=101);p.add_argument('--level',type=int,default=1);p.add_argument('--slowdown',type=float,default=1);p.add_argument('--variant',choices=VARIANTS,default='basic');p.add_argument('--chunk',type=int,default=1);p.add_argument('--workers',type=int,default=3);p.add_argument('--capacity',type=int,default=8);p.add_argument('--history',type=int,default=1);p.add_argument('--cadence',type=float,default=.2)
 p.add_argument('--resume-from',type=pathlib.Path)
 p.add_argument('--anchor',choices=['arrival','issue'],default='arrival')
 p.add_argument('--control',choices=['servo','waypoint','lane'],default='servo')
 p.add_argument('--reference-waypoints',action='store_true')
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
 if a.mode=='preflight':preflight(a.out)
 elif a.mode=='profile':profile(a,credential())
 elif a.mode=='sim':simulate(a)
 else:
  n=Native(a.out/'worker')
  try:
   samples=json.loads((a.samples/'samples.json').read_text());s=samples[0]
   ans,meta=n.act(prompt_for([s['state']],'basic',1,{'p50':1,'p95':1.5}),[(a.samples/s['image']).read_bytes()],a.out/'call');print(json.dumps({'commands':parse(ans),**meta}))
  finally:n.close()

if __name__=='__main__':main()
