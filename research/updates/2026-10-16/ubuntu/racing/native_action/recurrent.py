"""Carry only the last accepted GPT memory and own command history into new inputs."""
import json
import policy

def prompt(states,variant,chunk,anchor,delays,slowdown=1,camera='front',committed=None,memory='',past_commands=()):
 if any(r['t']>states[-1]['t_sim']+1e-9 for r in past_commands):raise ValueError('future commands in applied history')
 task=policy.prompt(states,variant,chunk,anchor,delays,slowdown,camera,committed)
 head,observations=task.split('\nVisible observations:',1)
 head=head.replace('Output ONLY the requested JSON actuator-command array.','Output ONLY the requested JSON object.')
 head=head.replace('Format:[[speed,steering,duration],...].','Format:{"scene":"short visual diagnosis","memory":"at most 35 words for your next decision","actions":[[speed,steering,duration],...]}.')
 head+='\nBefore selecting actions, inspect the newest IMAGE: name which way the road bends, the blue car heading versus road tangent, and nearest hazard. Put that diagnosis in scene (at most 35 words). Do not confuse the stripe being to one side with road curvature. Your memory should carry a useful driving correction from recent motion, not a fixed route. Update it when the new image contradicts it.'
 head+='\nLast ACCEPTED GPT memory (not ground truth):'+json.dumps(memory)+'\nPast ACTUALLY APPLIED actuator commands, absolute game times:'+json.dumps(list(past_commands),separators=(',',':'))
 return head+'\nVisible observations:'+observations

def parse(answer,count,anchor):
 obj=json.loads(answer.strip())
 if not isinstance(obj,dict) or set(obj)!={'scene','memory','actions'}:raise ValueError('recurrent output fields')
 if any(not isinstance(obj[k],str) or len(obj[k])>300 for k in ['scene','memory']):raise ValueError('recurrent text bounds')
 commands=policy.parse(json.dumps(obj['actions']),count,anchor)
 return commands,obj['memory'],obj['scene']
