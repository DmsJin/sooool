"""Blind timed delivery only. This module takes no images or observations."""
class Executor:
 def __init__(self):self.seq=-1;self.timeline=[]
 def offer(self,commands,issued,arrived,seq,anchor):
  if seq<=self.seq:return False
  self.seq=seq;t=issued if anchor=='issue' else arrived;timeline=[]
  for speed,steering,duration in commands:
   timeline.append((t,{'type':'drive','speed':speed,'steering':steering}));t+=duration
  timeline.append((t,{'type':'none'}))
  current=[x for x in timeline if x[0]<=arrived]
  self.timeline=([(arrived,current[-1][1])] if current else [])+[x for x in timeline if x[0]>arrived]
  return True
 def due(self,now):
  ready=[]
  while self.timeline and self.timeline[0][0]<=now:ready.append(self.timeline.pop(0)[1])
  return ready[-1] if ready else None
 def clear(self):self.timeline=[]
