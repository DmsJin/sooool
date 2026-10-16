"""Causal action chunks: a plan is visible only after its virtual response arrives."""
import concurrent.futures as cf
import heapq
from simulate import Scheduler


def parse_chunk(text, size):
 value=text.strip()
 if len(value)!=size or any(c not in '012345678' for c in value):
  raise ValueError(f'Expected exactly {size} action digits, each 0-8')
 actions=list(map(int,value))
 return {'chosen':actions[0],'chunk':actions}


class ChunkScheduler(Scheduler):
 def __init__(self,size,capacity=1):
  super().__init__(capacity)
  self.size=size;self.observation_frames={};self.plan=[];self.activated_at=None;self.plan_observation=None;self.step=-1

 def submit(self,frame,seq,action,delay,service):
  self.observation_frames[seq]=frame
  return super().submit(frame,seq,action,delay,service)

 def advance(self,frame):
  ready=[]
  while self.ready and self.ready[0][0]<=frame:ready.append(heapq.heappop(self.ready))
  if ready:
   _,seq,value=max(ready,key=lambda x:x[1])
   if seq>self.last:
    result=value.result() if isinstance(value,cf.Future) else value
    actions=result['chunk']
    if len(actions)!=self.size or any(type(a)!=int or not 0<=a<=8 for a in actions):
     raise ValueError('Invalid action chunk')
    self.last=seq;self.activated_at=frame;self.plan_observation=self.observation_frames[seq]
    self.plan=list(actions);self.step=-1
  if self.plan:
   step=min((frame-self.activated_at)//4,len(self.plan)-1)
   if step!=self.step:
    self.step=step;self.action=self.plan[step]
    self.applied.append({'frame':frame,'seq':self.last,'action':self.action,'chunk_step':step})
  return self.action

 def visible_plan(self,frame):
  if not self.plan:return None
  return {'observation_frame':self.plan_observation,'activated_frame':self.activated_at,
          'current_step':self.step,'remaining':[
           {'frame':self.activated_at+4*i,'action':a}
           for i,a in enumerate(self.plan) if self.activated_at+4*i>frame],
          'hold_after_end':self.plan[-1]}
