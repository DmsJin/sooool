"""Native integration check of a public-state wake; no model or score claim."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MUJOCO_GL','egl')
from core.episode import load_plugin
from core.sport import MatchConfig
from wait_watch import make_watch,wake_reason

def main():
 base=Path('/home/ubuntu/wzh/sooool-runtime');source=base/'stable-single-seed2'
 events=[json.loads(l) for l in (source/'episode.jsonl').read_text().splitlines()];cfg=MatchConfig(**next(e['cfg'] for e in events if e['ev']=='header'))
 sport=load_plugin(str(ROOT/'sports/tabletennis/plugin.py'));m=sport.build(cfg);timeline={}
 for e in events:
  if e.get('k',724)<724 and e['ev'] in ['cmd','resume']:timeline.setdefault(e['k'],[]).append(e)
 while m.k<724:
  for e in timeline.get(m.k,[]):
   if e['ev']=='cmd':m.apply(e['seat'],e['cmd'])
   else:m.resume()
  m.step()
 state=m.observe('A');assert state['ball_state']=='going to the opponent'
 option={'watch_for':{'ball_state':'coming to you','require_in_play':True,'max_steps':80}}
 watch=make_watch(option,state['point'],m.k);checked=0;reason=None
 while reason is None:
  state=m.observe('A');reason=wake_reason(watch,state,m.k);checked+=1
  if reason is None:m.step()
 assert reason=='incoming_public_referee'
 assert state['ball_in_play'] and state['ball_state']=='coming to you'
 timeout=make_watch(option,1,0)
 assert wake_reason(timeout,{'point':1,'ball_in_play':False,'ball_state':'coming to you'},79) is None
 assert wake_reason(timeout,{'point':1,'ball_in_play':False,'ball_state':'coming to you'},80)=='maximum_wait_elapsed'
 assert wake_reason(timeout,{'point':2},1)=='point_changed'
 report={'scope':'native passive public-referee watch diagnostic','start_step':724,'wake_step':m.k,'reason':reason,'public_status_checks':checked,'actions_after_watch_selected':0,'model_calls':0,'not_a_game_performance_result':True}
 (base/'wait-watch-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
if __name__=='__main__':main()
