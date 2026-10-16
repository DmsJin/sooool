"""Finite GPT lane goals with pixel feedback; never chooses a lane or route itself."""
import json,math
PROMPT='''Win two heats of this RoboRacer match by finishing one lap before the 1.75m/s opponent.
Inspect the attached real car images and legal observations. Yellow marks road centre,
magenta objects are obstacles, red/white walls bound the road. Positive y is LEFT.
Return ONLY one JSON row nested in an array: [[target_speed, lane_offset_left_m, lookahead_m]].
Speed must be [-1.5,4], lane offset [-0.85,0.85], lookahead [0.7,3.0], finite numbers.
A visual low-level executor tracks YOUR offset from the yellow centre stripe using fresh
camera measurements at5Hz. It never chooses a lane, route, obstacle maneuver or overtaking
maneuver. YOU decide those from these images. A curvature acceleration limit may lower
your speed on bends. The goal expires3 game seconds after THIS observation, then brakes.
On clear road choose speed3.2-3.8 and lookahead1.5-2.5. Choose a smooth safe lane and do
not cross another car. Initial lane is approximately+0.38m for inner and-0.38m for outer.
Inspect obstacles and choose the open side: a magenta object on the left needs a right
lane offset and vice versa. Keep an offset until safely past; avoid abrupt oscillation.
For tight bends slow to1.5-2.2; for a close obstruction brake before choosing an escape.
If stuck across observations despite forward commands, briefly reverse at-0.7 to-1.2.
Lane offset is relative to the YELLOW STRIPE, not relative to the current car.
Commit to your existing lane for overtaking: especially keep the initial outer-0.38
or inner+0.38 offset while passing the other car. Changing to the opposite offset
can cut into that car even if the latest delayed image appears clear. Switch only
when a fixed magenta obstacle forces a different lane and the new lane is clear.
Once the obstacle is passed, keep the new safe offset; do not automatically cross
back through another car. A bend alone is NOT a reason to switch lane offset.
The low-level curvature speed cap already slows turns: on open road prefer3.2-3.6,
including ordinary bends. Reserve1.5-2.2 for close hazards or recovery.
The low-level executor cannot detect obstacles or cars for you. Pending answers are unknown.
'''
def parse_lane(answer,count=1):
 rows=json.loads(answer.strip())
 if not isinstance(rows,list) or len(rows)!=1 or len(rows[0])!=3:raise ValueError('wrong lane goal shape')
 v,offset,look=map(float,rows[0])
 if not all(map(math.isfinite,(v,offset,look))) or not(-1.5<=v<=4 and -.85<=offset<=.85 and .7<=look<=3):raise ValueError('invalid lane goal')
 return [[v,offset,look]]
class Lane:
 def __init__(self):self.goal=None;self.expires=-1;self.seq=-1;self.seen=-1
 def clear(self):self.goal=None;self.expires=-1
 def offer(self,rows,origin,issued,seq,seen):self.goal=rows[0];self.expires=issued+3;self.seq=seq;self.seen=seen
 def local_points(self):return []
 def drive(self,now,metrics):
  if self.goal is None or now>=self.expires:return {'type':'none'}
  path=metrics.get('ground_path',[])
  if not path:return {'type':'none'}
  v,offset,look=self.goal;x,y=min(path,key=lambda p:abs(p[0]-look));y+=offset
  curvature=2*y/max(.04,x*x+y*y);steer=max(-.48,min(.48,math.atan(.46*curvature)))
  if v>0:v=min(v,math.sqrt(2.5/max(.001,abs(curvature))))
  return {'type':'drive','speed':round(v,6),'steering':round(steer,6)}
