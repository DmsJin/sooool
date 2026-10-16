"""Raw pixels and legal telemetry -> GPT actuator commands. No CV/controller."""
import json,math
BASE='''Win this Level1 RoboRacer match, first to win two one-lap heats. Opponent cruises at1.75m/s.
YOU must choose every speed and steering command directly from these camera images.
There is no lane follower, pure pursuit, image processor, automatic speed cap or obstacle controller.
Positive steering turns LEFT. Yellow is road centre; green is road; red/white walls bound it;
magenta shapes are fixed obstacles; blue is your car and orange is the opponent.
Use the provided image sequence and own telemetry to infer road shape, motion and steering response.
Camera: front240x160,70deg verticalFOV,pitched20deg down,height0.395m,offset0.22m forward.
Car wheelbase0.46m. Motor and steering targets are tracked with finite force.
Targets: speed[-1.5,4]m/s,steering[-0.48,0.48]rad,duration[0.05,1]game seconds.
The world continues while you think. Predict the car position and heading at action arrival.
Observe what the CURRENT held steering has already done; do not repeat a stale correction.
Keep a safe lane when passing, avoid cutting into the orange car; brake or reverse if stuck.
Output ONLY the requested JSON actuator-command array. Never call tools, inspect files, or return code.
'''
VARIANTS={
 'calibrated':'Separate lateral offset from road curvature: a stripe left of image centre may simply mean you occupy the right lane; it does not itself require a left turn. Infer heading from the distant road and both walls. Steering is an ANGLE, not a joystick: at2m/s, angle0.05rad turns heading about12deg per second,0.10 about25deg/s,0.20 about50deg/s. Most ordinary bends need small angles. Large sustained0.2-0.4 corrections can put the car into a wall before a fresh answer arrives. Predict the accumulated yaw over latency and upcoming plan duration, and unwind early. Reverse if forward speed remains near zero against a visible wall.',
 'predict':'Estimate motion between images. Predict the effect of the held command during latency, then choose a correction from that predicted frame. Countersteer before the car overshoots.',
 'geometry':'Use perspective and camera calibration mentally. Steering0.10rad corresponds roughly to radius4.6m;0.20rad to2.3m;0.30rad to1.5m. Choose steering for the visible bend, accounting for car travel while the answer is pending. No external geometry measurements are supplied.',
 'commit':'Keep the starting lane while passing: outer side means right of the yellow stripe, inner means left. A bend alone is not a reason to cross lanes. Use about2.6-3.2m/s on open road and1.5-2.2 before tight corners; correct heading early rather than weaving.',
 'gentle':'Prioritize staying on road:2.2-2.8m/s on straights,1.4-2.0 before bends. Use the image history to avoid oscillation. If the near stripe moves rapidly sideways, reduce steering before it reaches the opposite edge.'}
KEYS=('phase','done','t_sim','heat','heat_time_s','race','crashes_this_heat','results','own','race_over','world','step')
def visible(state):return {k:state[k] for k in KEYS if k in state}
def prompt(states,variant,chunk,anchor,delays,slowdown=1,camera='front',committed=None):
 s=BASE
 if camera=='chase':s=s.replace('Camera: front240x160,70deg verticalFOV,pitched20deg down,height0.395m,offset0.22m forward.','Camera: official chase240x160,70deg verticalFOV,pitched35.4deg down,height1.505m,offset1.5m behind. The blue car is YOU. Read its heading relative to the road; image right is the car right.')
 if camera=='dual':s=s.replace('Camera: front240x160,70deg verticalFOV,pitched20deg down,height0.395m,offset0.22m forward.','Each observation provides TWO original images, in order FRONT then CHASE. Front:240x160,70deg verticalFOV,pitch20deg down,height0.395m,offset0.22m forward. Chase:240x160,70deg verticalFOV,pitch35.4deg down,height1.505m,offset1.5m behind. The blue car is YOU. Both cameras rotate with your car. Infer imminent road curvature from FRONT and lateral room/body alignment from CHASE; neither image is a fixed world map.')
 s+='\n'+VARIANTS[variant]+f'\nSlowdown={slowdown}; real API latency seconds='+json.dumps(delays)+'. Divide real latency by slowdown for game-time delay. Pending model answers are unknown.'
 if anchor=='issue':s+=f'\nReturn exactly{chunk} commands, each duration1.0. The plan begins at the newest observation time: successive commands cover0-1s,1-2s,2-3s. The executor skips elapsed commands and brakes at the plan end; it never adjusts your numbers. Cover the future bend before you see it near the car.'
 else:s+=f'\nReturn exactly{chunk} commands. They begin on arrival and hold for their stated duration, then brake if no new plan arrives.'
 if committed is not None:s+='\nKnown actuator schedule (your earlier outputs, not predictions; absolute game times):'+json.dumps(committed,separators=(',',':'))+'. Use this to predict braking and already scheduled changes before arrival. New pending model outputs remain unknown.'
 return s+'\nFormat:[[speed,steering,duration],...].\nVisible observations:'+json.dumps([visible(x) for x in states],separators=(',',':'))
def parse(answer,count,anchor,max_duration=1):
 rows=json.loads(answer.strip())
 if not isinstance(rows,list) or len(rows)!=count:raise ValueError('command count')
 for row in rows:
  if not isinstance(row,list) or len(row)!=3 or any(type(x) not in (int,float) for x in row):raise ValueError('command shape/types')
  v,d,t=row
  if not all(math.isfinite(x) for x in row) or not(-1.5<=v<=4 and -.48<=d<=.48 and .05<=t<=max_duration):raise ValueError('command bounds')
  if anchor=='issue' and t!=1:raise ValueError('issue plan durations must be1s')
 return rows


def session_prompt(states,variant,chunk,anchor,delays,slowdown=1,camera='chase',committed=None,first=False,max_duration=1):
 if first:
  task=prompt(states,variant,chunk,anchor,delays,slowdown,camera,committed)
  head,obs=task.split('\nVisible observations:',1)
  head+='\nThis is one continuous driving conversation. Only ONE inference is outstanding. Every prior completed proposal in this conversation has already arrived; the current own command and committed schedule are authoritative. All prior plans are canceled at a new heat or when replaced. Remember how the car responded and improve your driving. If speed and held command are zero, the car remains stopped until an action arrives: do not predict travel at your newly requested speed before then.'
 else:
  head='Continue the same raw-camera driving policy. Current own telemetry and committed schedule are authoritative; canceled/replaced proposals are not executing. At a heat change the car and all prior schedules are reset. Images are oldest to newest. Real latency seconds:'+json.dumps(delays)+f'; slowdown={slowdown}. Committed future actuator schedule:'+json.dumps(committed or [],separators=(',',':'))
  slim=[{'t_sim':x['t_sim'],'heat':x['heat'],'own':{'forward_speed':x['own']['forward_speed'],'command':x['own']['command']}} for x in states[:-1]]+[visible(states[-1])]
  obs=json.dumps(slim,separators=(',',':'))
 head=head.replace('duration[0.05,1]',f'duration[0.05,{max_duration}]')
 if chunk==1:head+=f'\nReturn ONLY one row:[[speed,steering,duration]]. Plan begins on ARRIVAL. You may keep your exact command valid for up to{max_duration} game seconds; a fresh GPT command replaces it immediately. Prefer the longest valid duration when safe to avoid unnecessary expiry braking during inference. Use the conversation to learn the steering response and unwind corrections early. At the start you are already aligned with your assigned lane. Do not turn merely because the far road bends; choose steering for where the car will actually be when this action arrives. Never use tools or code.'
 else:head+=f'\nReturn ONLY exactly{chunk} rows:[[speed,steering,duration],...]. Plan begins on ARRIVAL. When safe, cover2.5-3 game seconds in total (each row duration<=1). Use distinct phases to enter, hold and unwind a bend; avoid a large fixed correction throughout. The next image decision starts after this response arrives and also needs another latency period. When uncertain, lower your speed. Never use tools or code.'
 return head+'\nVisible observations:'+obs
