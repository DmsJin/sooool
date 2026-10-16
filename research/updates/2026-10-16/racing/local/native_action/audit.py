"""Offline verify every simulator action is timed delivery of a GPT output."""
import argparse,collections,json,pathlib
from executor import Executor

def rows(path):return [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
def audit(d):
 cfg=json.loads((d/'config.json').read_text());end=json.loads((d/'summary.json').read_text());arrivals=collections.defaultdict(list);applied={}
 for r in rows(d/'arrivals.jsonl'):arrivals[r['due_step']].append(r)
 for r in rows(d/'applied.jsonl'):
  assert r['step'] not in applied,'multiple actions same step';applied[r['step']]=r
 resumes={r['k'] for r in rows(d/'episode.jsonl') if r.get('ev')=='resume'}
 e=Executor();checked=0
 for k in range(round(end['game_seconds']/.01)):
  if k in resumes:e.clear()
  if k in arrivals:
   r=max(arrivals[k],key=lambda r:r['seq']);e.offer(r['commands'],r['seen_step']*.01,k*.01,r['seq'],cfg['anchor'])
  expected=e.due(k*.01);actual=applied.get(k)
  assert (expected is None)==(actual is None),(k,'missing or extra command')
  if actual:
   assert e.seq==actual['seq']
   assert expected['type']==actual['command']['type']
   for key in ['speed','steering']:
    if key in expected:assert abs(expected[key]-actual['command'][key])<=1e-6,(k,'changed actuator',key)
   checked+=1
 inspected=0
 for f in d.glob('decision_*/input.json'):
  task=json.loads(f.read_text())['prompt'];observations=json.loads(task.split('Visible observations:',1)[1]);inspected+=1
  for o in observations:
   assert set(o)<=set(('phase','done','t_sim','heat','heat_time_s','race','crashes_this_heat','results','own','race_over','world','step'))
   assert set(o.get('own',{}))<=set(('grid','grid_side','forward_speed','command','held','retired'))
  assert 'camera_measurements' not in task
 return {'episode':d.name,'commands_checked':checked,'prompts_checked':inspected,'all_commands_exact_gpt_delivery':True,'no_hidden_observation_fields':True,'replay_matches':end['replay_matches']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);a=p.parse_args();result=[audit(d) for d in sorted(a.root.iterdir()) if d.is_dir() and (d/'summary.json').exists()];print(json.dumps(result,indent=2));(a.root/'actuator_audit.json').write_text(json.dumps(result,indent=2))
