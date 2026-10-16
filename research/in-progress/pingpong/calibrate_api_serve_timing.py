"""Fixed native branches for API serve timing; zero GPT performance claims."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MUJOCO_GL','egl')
from core.episode import load_plugin,header_cfg
from core.sport import parse_action,UNIT_OVER,FINISHED

def run(a):
 a.output.mkdir(parents=True,exist_ok=False)
 sport=load_plugin(str(ROOT/'sports/tabletennis/plugin.py'));layer=sport.action_layer('high');results=[]
 for source in a.source:
  events=[json.loads(l) for l in (source/'episode.jsonl').read_text().splitlines()]
  cfg=header_cfg(next(r for r in events if r['ev']=='header'))
  actions=[json.loads(l) for l in (source/'controller_actions.jsonl').read_text().splitlines()]
  windup=next(r for r in actions if r['action']['type']=='act');start=windup['reply']['took_effect']['step']
  toss=next(r for r in actions if r['action']['type']=='toss' and r['reply']['took_effect']['step']>start)
  actual_gap=toss['reply']['took_effect']['step']-start
  for gap in (10,12,14):
   for compensate in (False,True):
    m=sport.build(cfg);timeline={}
    for r in events:
     if r['ev'] in ('cmd','resume') and r['k']<start:timeline.setdefault(r['k'],[]).append(r)
    while m.k<start:
     for r in timeline.get(m.k,[]):
      if r['ev']=='cmd':m.apply(r['seat'],r['cmd'])
      else:m.resume()
     m.step()
    own=m.observe('A');assert own['you_serve'] and own['serve']['phase']=='open'
    body=dict(windup['action']);body['t']+=((gap-10)*m.dt if compensate else 0)
    parsed=parse_action(layer,'A',body,m,{});low,info=layer.lower('A',parsed,None,m);m.apply('A',low)
    while m.k<start+gap:m.step()
    parsed=parse_action(layer,'A',toss['action'],m,{});low,toss_info=layer.lower('A',parsed,None,m);m.apply('A',low)
    while m.k<start+500 and m.phase().state not in (UNIT_OVER,FINISHED):m.step()
    own=m.observe('A')
    result={'scope':'fixed native API-history branch; passive after serve; no GPT calls','seed':cfg.seed,'windup_step':start,'original_actual_toss_gap_ticks':actual_gap,'test_toss_gap_ticks':gap,'compensated_contact_time':compensate,'action_contact_in_s':body['t'],'end_step':m.k,'scores':m.scores(),'points':own['points'],'shots':own.get('shots'),'windup_feedback':{k:info.get(k) for k in ('blade_error_m','normal_error_deg','speed_scale','stroke')},'toss_feedback':toss_info}
    results.append(result);(a.output/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
