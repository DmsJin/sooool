"""GPT predicts arrival scene itself; code validates and logs, never drives from it."""
import json,math
import policy

def prompt(states,variant,chunk,anchor,delays,slowdown=1,camera='chase',committed=None,first=False):
 task=policy.session_prompt(states,variant,chunk,anchor,delays,slowdown,camera,committed,first);head,obs=task.split('\nVisible observations:',1)
 head=head.replace('Output ONLY the requested JSON actuator-command array.','Output ONLY the requested JSON object.').replace('Format:[[speed,steering,duration],...].','The actions field is an array of actuator rows.')
 head=head.replace(f'Return ONLY exactly{chunk} rows:[[speed,steering,duration],...].',f'Return ONLY a JSON object with the fields described below; actions contains exactly{chunk} rows.')
 head+='\nPredict your arrival state UNDER THE ALREADY COMMITTED CONTROLS, not your new requested actions. If stopped under a zero command, you stay stopped until a new action arrives. Estimate travel and accumulated yaw over the latency. road_turn_at_arrival describes the road under/just ahead of your predicted car, not a distant bend while you are still stationary. Inspect the road at that predicted location, not just the near stripe. A right bend now may be followed by a left bend before your response arrives (and vice versa); the first new action may need the opposite sign. Compare your earlier forecast with actual visible motion and revise mistakes.'
 head+='\nFormat:{"travel_before_arrival_m":number,"yaw_before_arrival_deg":number,"road_turn_at_arrival":"left|right|straight|blocked","actions":[[speed,steering,duration],...]}. Positive yaw is LEFT. Forecast fields describe motion BEFORE this plan arrives; actions execute AFTER arrival. Only your actions are sent; the executor never turns your forecast into controls.'
 return head+'\nVisible observations:'+obs

def parse(answer,count,anchor):
 obj=json.loads(answer.strip());keys={'travel_before_arrival_m','yaw_before_arrival_deg','road_turn_at_arrival','actions'}
 if not isinstance(obj,dict) or set(obj)!=keys:raise ValueError('forecast output fields')
 for k,lo,hi in [('travel_before_arrival_m',-20,20),('yaw_before_arrival_deg',-360,360)]:
  if type(obj[k]) not in (int,float) or not math.isfinite(obj[k]) or not lo<=obj[k]<=hi:raise ValueError('forecast field bounds')
 if obj['road_turn_at_arrival'] not in ('left','right','straight','blocked'):raise ValueError('forecast turn enum')
 commands=policy.parse(json.dumps(obj['actions']),count,anchor)
 return commands,{k:v for k,v in obj.items() if k!='actions'}
