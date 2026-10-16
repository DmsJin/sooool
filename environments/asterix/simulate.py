"""Event-driven virtual eight-worker Asterix; only native subscription model calls."""
import argparse,hashlib,heapq,io,json,pathlib,random,sys,time
from collections import deque

class Scheduler:
 def __init__(self,capacity=8):
  self.free=[0]*capacity;self.ready=[];self.last=-1;self.action=0;self.peak=0;self.applied=[]
 def advance(self,frame):
  ready=[]
  while self.ready and self.ready[0][0]<=frame:ready.append(heapq.heappop(self.ready))
  newest=max(ready,key=lambda x:x[1]) if ready else None
  for due,seq,action in ready:
   apply=newest[1]==seq and seq>self.last
   if apply:self.last=seq;self.action=action;self.applied.append({'frame':frame,'seq':seq,'action':action})
  return self.action
 def available(self,frame):return next((i for i,v in enumerate(self.free) if v<=frame),None)
 def submit(self,frame,seq,action,delay,service):
  slot=self.available(frame)
  if slot is None:raise ValueError('All virtual workers busy')
  self.free[slot]=frame+max(1,service)
  heapq.heappush(self.ready,(frame+max(1,delay),seq,action))
  self.peak=max(self.peak,sum(v>frame for v in self.free));return slot

BASE='''Play Atari Asterix. Collect useful objects and avoid lyres. Return only one integer: 0=NOOP, 1=UP, 2=RIGHT, 3=LEFT, 4=DOWN, 5=UPRIGHT, 6=UPLEFT, 7=DOWNRIGHT, 8=DOWNLEFT.
The virtual game runs at 7.5 raw frames per second, one eighth normal speed. Images are chronological, sampled every 4 raw frames. At most eight requests are in flight; observations are dropped when all workers are busy. A command becomes available only after a sampled response delay. The newest completed observation wins and stale commands are discarded. The last action is held until replaced. Your actual wall-clock thinking time does not advance this simulation. Do not use tools, explain, or analyze aloud. Output the action integer immediately.
'''
STRATEGY='''Prioritize survival and useful pickups. Locate the controlled player and compare the three images to infer each nearby object's direction. Distinguish harmful lyres from collectibles rather than chasing every object. Plan for the player's and objects' positions when the delayed command arrives, including motion under the currently held action. Prefer a safe intercept of a collectible. Avoid moving through a hazard's lane or oscillating between rows. If a safe row has no immediate opportunity, keep a safe position instead of holding a vertical direction indefinitely. Output only the action integer.
'''

def png(obs):
 from PIL import Image
 buf=io.BytesIO();Image.fromarray(obs).resize((224,224),Image.Resampling.BILINEAR).save(buf,format='PNG');return buf.getvalue()

def parse_action(text):
 s=text.strip()
 if s in [str(i) for i in range(9)]:return int(s)
 obj=json.loads(s)
 if isinstance(obj,dict) and set(obj)=={'action'} and type(obj['action']) is int and 0<=obj['action']<9:return obj['action']
 raise ValueError('Invalid action: '+repr(s))

def run(args):
 import gymnasium as gym,ale_py
 from subscription_client import SubscriptionClient
 sys.path.insert(0,str(args.suite/'code'))
 from latency_bench.latency.samplers import build_sampler
 from latency_bench.core.clock import EnvClock
 gym.register_envs(ale_py)
 manifest=json.loads(args.profile.read_text());summary=manifest['summary']
 out=args.output;out.mkdir(parents=True,exist_ok=False)
 (out/'config.json').write_text(json.dumps({**vars(args),'profile':str(args.profile),'suite':str(args.suite),'output':str(out),
  'virtual_fps':7.5,'normal_game_fps':60,'concurrency_limit':8,'obs_stride':4,'auth':'ChatGPT subscription',
  'latency_method':'iid pooled fitted emissions','api_calls':0,'history':'fresh native thread per observation; only supplied three images and applied action state',
  'latency_draws_hidden_from_model':True},indent=2))
 client=None if args.random else SubscriptionClient(args.suite,out)
 results=[]
 try:
  for variant in args.variants.split(','):
   if variant not in ('baseline','anticipate'):raise ValueError(variant)
   sampler=build_sampler({'method':'iid','profile_path':str(args.profile),'seed':42+args.seed},clock=EnvClock(env_fps=7.5,obs_fps=1.875))
   env=gym.make('ALE/Asterix-v5',render_mode='rgb_array',obs_type='rgb',frameskip=1,repeat_action_probability=0.,full_action_space=False,mode=0,difficulty=0,max_num_frames_per_episode=108000)
   obs,info=env.reset(seed=args.seed);noops=int(env.unwrapped.np_random.integers(1,31))
   for _ in range(noops):
    obs,_,done,truncated,info=env.step(0)
    if done or truncated:obs,info=env.reset()
   directory=out/variant;directory.mkdir();window=deque(maxlen=3);scheduler=Scheduler();score=0.;calls=0;drops=0;started=time.perf_counter();rng=random.Random(args.seed)
   profile_text=f"Measured Ultrafast complete-response delay: mean {summary['mean_ms']:.0f} ms, median {summary['p50_ms']:.0f} ms, P95 {summary['p95_ms']:.0f} ms. The actual delay of your request is unknown.\n"
   (directory/'prompt.txt').write_text(BASE+profile_text+(STRATEGY if variant=='anticipate' else ''))
   with (directory/'decisions.jsonl').open('w') as log:
    for frame in range(args.max_frames):
     action=scheduler.advance(frame)
     if frame%4==0:
      window.append((frame,png(obs)))
      if scheduler.available(frame) is None:drops+=1
      else:
       # Sample timing independently, but never expose it or a future command.
       timing=sampler.sample({'episode_id':args.seed,'worker_slot':0})
       prompt=BASE+profile_text+(STRATEGY if variant=='anticipate' else '')+f'Current observation frame: {frame}. Image frames: {[f for f,_ in window]}. Current held action: {action}.\n'
       if args.random:chosen=rng.randrange(9);meta={};answer=str(chosen)
       else:
        answer,meta=client.act(prompt,[im for _,im in window],directory/f'decision_{calls:05d}');chosen=parse_action(answer)
       slot=scheduler.submit(frame,calls,chosen,timing.action_ready_raw_frames,timing.worker_service_raw_frames)
       log.write(json.dumps({'decision':calls,'obs_frame':frame,'image_frames':[f for f,_ in window],
           'image_sha256':[hashlib.sha256(im).hexdigest() for _,im in window],'held_action':action,'chosen':chosen,
           'sampled_delay_ms':timing.latency_ms,'action_ready_frame':frame+timing.action_ready_raw_frames,
           'virtual_worker_slot':slot,'score_at_issue':score,'answer':answer,**meta})+'\n');log.flush();calls+=1
       if calls%20==0:print('PROGRESS '+json.dumps({'variant':variant,'seed':args.seed,'calls':calls,'game_seconds':frame/60,'score':score,'wall_seconds':time.perf_counter()-started,'api_spend_usd':0}),flush=True)
     obs,reward,done,truncated,info=env.step(action);score+=reward
     if done or truncated:break
   env.close()
   result={'variant':variant,'seed':args.seed,'score':score,'frames':frame+1,'game_seconds':(frame+1)/60,'lives':info.get('lives'),
           'calls':calls,'drops':drops,'peak_virtual_inflight':scheduler.peak,'wall_seconds':time.perf_counter()-started,
           'status':'natural_end' if done or truncated else 'horizon','api_spend_usd':0}
   (directory/'summary.json').write_text(json.dumps(result,indent=2));(directory/'actions.json').write_text(json.dumps(scheduler.applied));results.append(result)
   print('EPISODE '+json.dumps(result),flush=True)
 except BaseException as exc:
  (out/'failure.json').write_text(json.dumps({'type':type(exc).__name__,'error':str(exc),'api_spend_usd':0},indent=2));raise
 finally:
  if client:client.close()
  (out/'summary.json').write_text(json.dumps({'episodes':results,'api_spend_usd':0},indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--suite',type=pathlib.Path,required=True);p.add_argument('--profile',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--seed',type=int,default=2);p.add_argument('--variants',default='baseline,anticipate');p.add_argument('--max-frames',type=int,default=3600);p.add_argument('--random',action='store_true');run(p.parse_args())
