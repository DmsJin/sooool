"""Finite GPT waypoint plans tracked using own-speed/command dead reckoning only.

The executor never sees images or simulator positions. Every destination and speed
comes from a GPT plan, in the coordinate frame of its observation. A stale plan
expires and brakes; it cannot keep driving without new model decisions.
"""
import json,math


def parse_points(answer,count=3):
 s=answer.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
 rows=json.loads(s)
 if not isinstance(rows,list) or len(rows)!=count:raise ValueError('wrong waypoint count')
 out=[]
 for row in rows:
  if not isinstance(row,list) or len(row)!=3:raise ValueError('wrong waypoint shape')
  x,y,v=map(float,row)
  if not all(map(math.isfinite,(x,y,v))) or not(-3<=x<=10 and -5<=y<=5 and -1.5<=v<=4):raise ValueError('invalid waypoint')
  out.append([x,y,v])
 return out


class Ego:
 def __init__(self):self.x=self.y=self.yaw=0.0
 def pose(self):return self.x,self.y,self.yaw
 def update(self,speed,steering,dt):
  omega=speed*math.tan(steering)/.46
  heading=self.yaw+omega*dt/2
  self.x+=speed*math.cos(heading)*dt;self.y+=speed*math.sin(heading)*dt
  self.yaw+=omega*dt


class Tracker:
 def __init__(self,ego):self.ego=ego;self.points=[];self.expires=-1;self.seq=-1;self.seen=-1
 def offer(self,points,origin,issued,seq,seen):
  x,y,yaw=origin;c,s=math.cos(yaw),math.sin(yaw)
  self.points=[(x+c*px-s*py,y+s*px+c*py,v) for px,py,v in points]
  self.expires=issued+3;self.seq=seq;self.seen=seen
 def clear(self):self.points=[];self.expires=-1
 def local_points(self):
  x,y,yaw=self.ego.pose();c,s=math.cos(yaw),math.sin(yaw)
  return [(c*(px-x)+s*(py-y),-s*(px-x)+c*(py-y),v) for px,py,v in self.points]
 def drive(self,now,own_speed):
  if now>=self.expires or not self.points:return {'type':'none'}
  points=self.local_points();direction=-1 if points[0][2]<0 else 1
  ahead=[p for p in points if p[0]*direction>.1]
  if not ahead:return {'type':'none'}
  lookahead=1.2+.35*abs(own_speed)
  x,y,v=min(ahead,key=lambda p:abs(math.hypot(p[0],p[1])-lookahead))
  steer=math.atan2(.92*y,max(.04,x*x+y*y))
  return {'type':'drive','speed':round(v,6),'steering':round(max(-.48,min(.48,steer)),6)}


PROMPT='''Win this RoboRacer match by finishing one lap ahead of the opponent and winning two heats.
You see the real car camera images and legal telemetry. Yellow is the road centre, magenta is an obstacle;
red/white walls bound the road. At level 1 the opponent cruises at 1.75 m/s, so slow following loses.
Return ONLY exactly three [forward_metres,left_metres,target_speed_m_s] waypoints in the CURRENT image's
car coordinate frame. These are destinations, NOT steering angles or durations. Each speed is [-1.5,4].
Each forward coordinate must be in [-3,10] metres and each left coordinate in [-5,5] metres.
All entries must be finite numbers. Do not put a destination outside these bounds.
On clear road choose approximately 2m, 4m, 6m forward points along a smooth safe lane, with speeds 2.5-3.8.
Choose points along the bend when curving. Inspect the images for cars and pass through a clear lane.
Image-derived ground points are noisy measurements, not world positions. Your own grid side suggests
an initial lane offset from the yellow centre of +0.38m for inner or -0.38m for outer.
A low-level executor follows YOUR waypoint destinations and speeds, using only own-speed dead reckoning.
It compensates motion while your answer was pending; it cannot independently see or follow the road.
The plan is valid for 3 GAME seconds from the observation, then it brakes without a fresh model plan.
If forward motion stays near zero despite a forward command across several observations, choose a
short reverse destination (negative forward coordinate and negative speed), then rejoin the road.
Pending model answers are unknown. Cover the visible path far enough ahead for the stated inference delay.
'''
