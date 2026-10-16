"""Same virtual game semantics; overlap independent subscription computations."""
import dataclasses,math
import argparse,concurrent.futures as cf,hashlib,heapq,json,pathlib,random,sys,threading,time
from collections import deque
from simulate import Scheduler,BASE,STRATEGY,png,parse_action
from chunk_control import ChunkScheduler,parse_chunk

LANES='''Asterix moves continuously left/right but up/down jumps between rows. Objects travel horizontally. Locate the player before choosing a direction, and compare images for incoming lyres. A safe plan should remain safe during the current held motion and the roughly seven raw frames before your next command can apply. Prefer a nearby collectible on a safe row; avoid chasing distant objects across multiple hazard rows. Stop vertical movement once aligned with a safe row instead of sweeping continuously through rows. Use the recently applied actions below to avoid reversing an unfinished maneuver without a new hazard. Output only the integer action.\n'''

IDENTIFY=STRATEGY+'''Visual identification: the controlled player is the small yellow character matching the yellow remaining-life icon below the arena. Locate that character in the newest image; the icon below the arena is not an in-game target. Do not mistake the player for an incoming object. Stationary white score popups such as 50 are feedback, not moving collectibles to chase. Use actual sprite shapes and motion to distinguish useful incoming objects from lyres. Output only the action integer.\n'''

COMPACT="""The player is yellow; white score popups are not targets. Objects move horizontally; UP/DOWN changes rows. Anticipate motion during the response delay and current held action. Intercept nearby safe collectibles, avoid lyres. Once aligned, release vertical motion. Use recent applied actions to maintain a maneuver unless a new hazard requires changing it.
"""

WAVES=COMPACT+"""Lyres often form a moving column across several rows. Do not cross that column during a row change. Prefer changing rows just after the column passes your horizontal position, then intercept a collectible from behind the hazards. Account for the column's motion during your response delay.
"""

GUARD=LANES+"""Check that the destination row remains safe not only when your command arrives, but also through the next observation interval (four more raw frames). Avoid entering a row where an approaching lyre will reach your projected horizontal position within that interval. In these images, pale pink pronged shapes are lyres; solid red rounded containers are useful pickups. Keep collecting nearby safe items rather than waiting on an empty row when an adjacent row is clear.
"""

# Prompt-only variants: identical images, controller, latency and action-history format.
PIPELINE=GUARD.replace(
 'A safe plan should remain safe during the current held motion and the roughly seven raw frames before your next command can apply.',
 'Your command arrives roughly seven raw frames later. Older pending requests can change the held action meanwhile; their answers are unknown. Choose a move safe despite that uncertainty.'
).replace(
 'Stop vertical movement once aligned with a safe row instead of sweeping continuously through rows.',
 'Request release of vertical movement before overshooting a safe row: release is delayed too. Do not repeat a row change just because its effect is not visible yet.'
)
INTERCEPT=GUARD.replace(
 'Prefer a nearby collectible on a safe row; avoid chasing distant objects across multiple hazard rows.',
 'Prefer intercepting an approaching collectible on your current or adjacent safe row. Keep near the horizontal middle when safe; avoid chasing departing objects to the edges.'
).replace(
 'Keep collecting nearby safe items rather than waiting on an empty row when an adjacent row is clear.',
 'Move toward the next safe intercept after a pickup; wait briefly if an incoming lyre blocks that path.'
)

CENTER=LANES+"""Prefer the middle third of the screen horizontally. Intercept approaching collectibles by choosing a safe row before they reach your column; avoid chasing departing objects toward the edges. Before changing rows, check incoming lyres in the destination row over the response delay plus the next four raw frames.
"""

def parse_intent(text):
 value=text.strip()
 if len(value)!=2 or any(d not in '012345678' for d in value):raise ValueError('Expected two digits: action and target row')
 return {'chosen':int(value[0]),'goal_row':int(value[1])}

def scale_latency(sample,factor):
 if not math.isfinite(factor) or factor<1:raise ValueError('Sensitivity multiplier must be finite and >= 1')
 if factor==1:return sample
 delay=sample.latency_ms*factor;service=sample.worker_service_ms*factor
 return dataclasses.replace(sample,latency_ms=delay,worker_service_ms=service,
  latency_raw_frames=math.ceil(delay*7.5/1000),action_ready_raw_frames=math.ceil(delay*7.5/1000),worker_service_raw_frames=math.ceil(service*7.5/1000))

class FutureScheduler(Scheduler):
 def __init__(self,vertical_limit=None,fresh_vertical=False,capacity=8):
  super().__init__(capacity);self.vertical_limit=vertical_limit;self.applied_at=None;self.goal_row=8
  self.fresh_vertical=fresh_vertical;self.vertical_finished=-1;self.observation_frames={}
 def submit(self,frame,seq,action,delay,service):
  self.observation_frames[seq]=frame
  return super().submit(frame,seq,action,delay,service)
 def advance(self,frame):
  ready=[]
  while self.ready and self.ready[0][0]<=frame:ready.append(heapq.heappop(self.ready))
  if ready:
   due,seq,value=max(ready,key=lambda x:x[1])
   if seq>self.last:
    result=value.result() if isinstance(value,cf.Future) else {'chosen':value}
    self.action=result['chosen']
    suppressed=False
    if self.fresh_vertical and self.action in (1,4,5,6,7,8):
     if self.observation_frames[seq]<self.vertical_finished:
      self.action={1:0,4:0,5:2,6:3,7:2,8:3}[self.action];suppressed=True
     else:self.vertical_finished=frame+self.vertical_limit
    if 'goal_row' in result:self.goal_row=result['goal_row']
    self.last=seq;self.applied_at=frame;self.applied.append({'frame':frame,'seq':seq,'action':self.action})
    if suppressed:self.applied[-1]['reason']='vertical_requires_fresh_observation'
    if 'goal_row' in result:self.applied[-1]['goal_row']=self.goal_row
  if self.vertical_limit is not None and self.applied_at is not None and frame-self.applied_at>=self.vertical_limit and self.action in (1,4,5,6,7,8):
   self.action={1:0,4:0,5:2,6:3,7:2,8:3}[self.action]
   self.applied.append({'frame':frame,'seq':self.last,'action':self.action,'reason':'vertical_timeout'})
  return self.action

class NativePool:
 def __init__(self,suite,out,workers):
  self.suite=suite;self.out=out;self.local=threading.local();self.clients=[];self.lock=threading.Lock()
  self.pool=cf.ThreadPoolExecutor(max_workers=workers)
 def request(self,prompt,images,directory,goal_mode=False,chunk_size=1):
  from subscription_client import SubscriptionClient
  if not hasattr(self.local,'client'):
   with self.lock:
    ident=len(self.clients);target=self.out/f'client_{ident}';target.mkdir()
    client=SubscriptionClient(self.suite,target);self.clients.append(client)
   self.local.client=client
  answer,meta=self.local.client.act(prompt,images,directory)
  parsed=parse_chunk(answer,chunk_size) if chunk_size>1 else (parse_intent(answer) if goal_mode else {'chosen':parse_action(answer)})
  result={'answer':answer,**parsed,**meta}
  (directory/'policy_result.json').write_text(json.dumps(result,indent=2));return result
 def submit(self,*args):return self.pool.submit(self.request,*args)
 def close(self):
  self.pool.shutdown(wait=True)
  for c in self.clients:c.close()

def run(args):
 import gymnasium as gym,ale_py
 sys.path.insert(0,str(args.suite/'code'))
 from latency_bench.latency.samplers import build_sampler
 from latency_bench.core.clock import EnvClock
 gym.register_envs(ale_py)
 out=args.output;out.mkdir(parents=True,exist_ok=False)
 manifest=json.loads(args.profile.read_text());summary=dict(manifest['summary'])
 if args.chunk_size>1:
  if args.variants!='compact_spaced':raise ValueError('Chunk comparison freezes the compact_spaced policy')
  if args.chunk_replan_actions is not None and not 1<=args.chunk_replan_actions<=args.chunk_size:raise ValueError('chunk-replan-actions must be between one and chunk-size')
  args.decision_stride=4*(args.chunk_replan_actions or args.chunk_size)
 if args.virtual_capacity<1:raise ValueError('virtual-capacity must be positive')
 if args.decision_stride<4 or args.decision_stride%4:raise ValueError('decision-stride must be a positive multiple of four')
 if not math.isfinite(args.latency_scale) or args.latency_scale<1:raise ValueError('latency-scale must be finite and >=1')
 for key in ('mean_ms','p50_ms','p95_ms'):summary[key]*=args.latency_scale
 replay=[] if args.replay_prefix is None else [json.loads(x) for x in args.replay_prefix.read_text().splitlines()]
 if replay and ',' in args.variants:raise ValueError('Replay prefix is for exactly one variant')
 config={k:str(v) if isinstance(v,pathlib.Path) else v for k,v in vars(args).items()}
 config.update(auth='ChatGPT subscription',virtual_fps=7.5,normal_game_fps=60,virtual_capacity=args.virtual_capacity,observation_stride=4,
  latency_method='iid pooled fitted emissions',api_spend_usd=0,real_computation_concurrency=args.native_workers,
  history='fresh native thread; three current images; lanes also receives eight previously applied actions',future_information='never provided')
 (out/'config.json').write_text(json.dumps(config,indent=2))
 for source in ('simulate_async.py','simulate.py','subscription_client.py','chunk_control.py'):(out/source).write_text(pathlib.Path(__file__).with_name(source).read_text())
 pool=None if args.random else NativePool(args.suite,out,args.native_workers);results=[]
 try:
  for variant in args.variants.split(','):
   extras={'baseline':'','anticipate':STRATEGY,'lanes':LANES,'identify':IDENTIFY,'pulse':'','spaced':IDENTIFY,'compact':COMPACT,'compact_spaced':COMPACT,'compact_spaced_hop':COMPACT,'waves':WAVES,'lanes_guard':GUARD,'guard_pipeline':PIPELINE,'guard_intercept':INTERCEPT,'intent':LANES,'center':CENTER}
   if variant not in extras:raise ValueError(variant)
   spaced=variant in ('spaced','compact_spaced','compact_spaced_hop','waves')
   hop=variant=='compact_spaced_hop'
   sampler=build_sampler({'method':'iid','profile_path':str(args.profile),'seed':42+args.seed},clock=EnvClock(env_fps=7.5,obs_fps=1.875))
   env=gym.make('ALE/Asterix-v5',render_mode='rgb_array',obs_type='rgb',frameskip=1,repeat_action_probability=0.,full_action_space=False,mode=0,difficulty=0,max_num_frames_per_episode=108000)
   obs,info=env.reset(seed=args.seed);noops=int(env.unwrapped.np_random.integers(1,31))
   for _ in range(noops):
    obs,_,done,truncated,info=env.step(0)
    if done or truncated:obs,info=env.reset()
   directory=out/variant;directory.mkdir();window=deque(maxlen=9 if spaced else 3)
   scheduler=ChunkScheduler(args.chunk_size,args.virtual_capacity) if args.chunk_size>1 else FutureScheduler(vertical_limit=4 if variant=='pulse' or hop else None,fresh_vertical=hop,capacity=args.virtual_capacity)
   score=0.;calls=0;drops=0;started=time.perf_counter();rng=random.Random(args.seed);requests=[];executed_frames=0;controlled_skips=0
   profile_text=f"Measured Ultrafast complete-response delay: mean {summary['mean_ms']:.0f} ms, median {summary['p50_ms']:.0f} ms, P95 {summary['p95_ms']:.0f} ms. The actual delay of your request is unknown.\n"
   if args.latency_scale!=1:profile_text=profile_text.replace('Measured Ultrafast complete-response delay:', 'Hypothetical slower response delay for sensitivity testing:')
   base=BASE+profile_text+extras[variant]
   if args.virtual_capacity!=8:base=base.replace('At most eight requests are in flight',f'At most {args.virtual_capacity} request(s) may be in flight')
   if args.latency_scale!=1:base=base.replace('roughly seven raw frames',f"roughly {summary['mean_ms']*7.5/1000:.1f} raw frames")
   if variant=='pulse':base=base.replace('The last action is held until replaced.', 'The last action is held until replaced, except its UP/DOWN component automatically releases after 4 raw frames; any LEFT/RIGHT component continues. A new command restarts this four-frame allowance. Plan short row changes accordingly.')
   if hop:base=base.replace('The last action is held until replaced.', 'UP/DOWN lasts at most four raw frames, then releases; LEFT/RIGHT continues. Further vertical commands based on observations before that hop finished have their vertical component ignored. Wait for a fresh observation before requesting another row change.')
   if spaced:base=base.replace('Images are chronological, sampled every 4 raw frames.', 'Images are chronological; use their frame timestamps. The supplied history spans up to 32 raw frames, with the middle image 8 raw frames old and the newest image current.')
   if args.decision_stride!=4:base+=f'Images are captured every 4 raw frames; new model requests are attempted every {args.decision_stride} raw frames.\n'
   if args.chunk_size>1:
    base=base.replace('Return only one integer:', 'Action digit mapping:').replace('Output the action integer immediately.',f'Output exactly {args.chunk_size} action digits immediately, without punctuation.')
    base=base.replace('The last action is held until replaced.',f'A response starts a sequence of {args.chunk_size} actions; each lasts four raw frames. The final action is held after the sequence ends until a new response arrives. A new response replaces the remaining old sequence.')
    base+='Plan from your predicted position when this delayed response arrives, then plan each subsequent four-frame interval. Previously returned scheduled actions continue during this request; their known schedule is provided below. Never assume an unfinished request has already returned.\n'
    if args.hide_chunk_plan:base=base.replace('their known schedule is provided below.', 'their future schedule is omitted in this ablation.')
   if variant=='intent':
    base=base.replace('Return only one integer:', 'Action digit mapping:').replace('Output only the integer action.', '').replace('Output the action integer immediately.', 'Output the two-digit code immediately.')
    base+='Return exactly two digits, no punctuation: first is the action (0-8); second is the target row (0=top through 7=bottom, 8=no target). Example: 23 means RIGHT toward row 3. Preserve a useful safe target until a pickup, then choose another; change it if unsafe or no longer useful. The next observation receives only the last applied target, not pending decisions.\n'
   (directory/'prompt.txt').write_text(base)
   with (directory/'issued.jsonl').open('w') as issued:
    for frame in range(args.max_frames):
     action=scheduler.advance(frame)
     if frame%4==0:
      window.append((frame,png(obs)))
      selected=list(window)
      if spaced:selected=[selected[i] for i in sorted({0,max(0,len(selected)-3),len(selected)-1})]
      if frame%args.decision_stride:controlled_skips+=1
      elif scheduler.available(frame) is None:drops+=1
      else:
       timing=scale_latency(sampler.sample({'episode_id':args.seed,'worker_slot':0}),args.latency_scale)
       prompt=base+f'Current observation frame: {frame}. Image frames: {[f for f,_ in selected]}. Current held action: {action}.\n'
       if variant=='lanes':prompt+='Recently applied commands, oldest first: '+json.dumps(scheduler.applied[-8:])+'.\n'
       if variant in ('compact','compact_spaced','compact_spaced_hop','waves','lanes_guard','guard_pipeline','guard_intercept','intent','center'):
        prompt+='Applied commands, oldest first, age_in_raw_frames:action: '+','.join(str(frame-x['frame'])+':'+str(x['action']) for x in scheduler.applied[-8:])+'.\n'
       if variant=='intent':prompt+=f'Last committed target row: {scheduler.goal_row}.\n'
       known_plan=scheduler.visible_plan(frame) if args.chunk_size>1 else None
       if args.chunk_size>1 and not args.hide_chunk_plan:
        prompt+='Previously returned plan (raw frame timestamps): '+json.dumps(known_plan,separators=(',',':'))+'.\n'
       if calls<len(replay):
        previous=replay[calls]
        checks={'decision':calls,'obs_frame':frame,'held_action':action,'image_sha256':[hashlib.sha256(im).hexdigest() for _,im in selected],'sampled_delay_ms':timing.latency_ms}
        if args.chunk_size>1:checks.update(known_plan_at_issue=known_plan,plan_visible_to_policy=not args.hide_chunk_plan)
        if any(previous[k]!=v for k,v in checks.items()):raise ValueError('Replay mismatch before any new model call at '+str(calls))
        future=cf.Future();future.set_result({**previous,'replayed_without_model_call':True})
       elif args.replay_only:break
       elif args.random:
        future=cf.Future();chunk=[rng.randrange(9) for _ in range(args.chunk_size)];future.set_result({'chosen':chunk[0],'answer':''.join(map(str,chunk)),**({'chunk':chunk} if args.chunk_size>1 else {})})
       else:future=pool.submit(prompt,[im for _,im in selected],directory/f'decision_{calls:05d}',variant=='intent',args.chunk_size)
       slot=scheduler.submit(frame,calls,future,timing.action_ready_raw_frames,timing.worker_service_raw_frames)
       row={'decision':calls,'obs_frame':frame,'image_frames':[f for f,_ in selected],'held_action':action,
            'image_sha256':[hashlib.sha256(im).hexdigest() for _,im in selected],'sampled_delay_ms':timing.latency_ms,
            'action_ready_frame':frame+timing.action_ready_raw_frames,'virtual_worker_slot':slot,'score_at_issue':score}
       if args.chunk_size>1:row['known_plan_at_issue']=known_plan;row['plan_visible_to_policy']=not args.hide_chunk_plan
       requests.append((row,future));issued.write(json.dumps(row)+'\n');issued.flush();calls+=1
       if calls%20==0:print('PROGRESS '+json.dumps({'variant':variant,'seed':args.seed,'calls':calls,'game_seconds':frame/60,'score':score,'wall_seconds':time.perf_counter()-started,'api_spend_usd':0}),flush=True)
     obs,reward,done,truncated,info=env.step(action);score+=reward;executed_frames=frame+1
     if done or truncated:break
   env.close()
   # Drain already-issued subscription calls without applying post-terminal actions.
   with (directory/'decisions.jsonl').open('w') as log:
    for row,future in requests:log.write(json.dumps({**row,**future.result()})+'\n')
   result={'variant':variant,'seed':args.seed,'score':score,'frames':executed_frames,'game_seconds':executed_frames/60,'lives':info.get('lives'),
           'calls':calls,'drops':drops,'controlled_observation_skips':controlled_skips,'decision_stride':args.decision_stride,'chunk_size':args.chunk_size,'chunk_replan_actions':args.chunk_replan_actions,'virtual_capacity':args.virtual_capacity,'hide_chunk_plan':args.hide_chunk_plan,'peak_virtual_inflight':scheduler.peak,'wall_seconds':time.perf_counter()-started,
           'status':'replay_prefix_verified' if args.replay_only else ('natural_end' if done or truncated else 'horizon'),'api_spend_usd':0,'replayed_calls':min(calls,len(replay)),'diagnostic_warm_start':args.warm_start}
   (directory/'summary.json').write_text(json.dumps(result,indent=2));(directory/'actions.json').write_text(json.dumps(scheduler.applied));results.append(result)
   print('EPISODE '+json.dumps(result),flush=True)
 except BaseException as exc:
  # Preserve the contiguous completed prefix for deterministic offline recovery.
  if 'requests' in locals():
   with (directory/'completed_prefix.jsonl').open('w') as prefix:
    for row,future in requests:
     if not future.done() or future.cancelled() or future.exception() is not None:break
     prefix.write(json.dumps({**row,**future.result()})+'\n')
  (out/'failure.json').write_text(json.dumps({'type':type(exc).__name__,'error':str(exc),'api_spend_usd':0},indent=2));raise
 finally:
  if pool:pool.close()
  (out/'summary.json').write_text(json.dumps({'episodes':results,'api_spend_usd':0},indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--suite',type=pathlib.Path,required=True);p.add_argument('--profile',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--seed',type=int,default=2);p.add_argument('--variants',default='lanes');p.add_argument('--max-frames',type=int,default=3600);p.add_argument('--native-workers',type=int,default=3);p.add_argument('--decision-stride',type=int,default=4);p.add_argument('--chunk-size',type=int,choices=(1,4,8),default=1);p.add_argument('--chunk-replan-actions',type=int);p.add_argument('--virtual-capacity',type=int,default=8);p.add_argument('--hide-chunk-plan',action='store_true');p.add_argument('--warm-start',action='store_true');p.add_argument('--latency-scale',type=float,default=1.);p.add_argument('--random',action='store_true');p.add_argument('--replay-prefix',type=pathlib.Path);p.add_argument('--replay-only',action='store_true');run(p.parse_args())
