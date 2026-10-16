"""Branch replay diagnostic of return kinematics. No GPT performance claim.
Restores native prior command log; alternatives use only recorded allowed menus.
"""
import argparse,json,os,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MUJOCO_GL','egl')
from core.episode import load_plugin
from core.sport import MatchConfig,parse_action,UNIT_OVER,FINISHED

def run(a):
 a.output.mkdir(parents=True,exist_ok=False)
 events=[json.loads(line) for line in (a.source/'episode.jsonl').read_text().splitlines()]
 header=next(e for e in events if e['ev']=='header');cfg=MatchConfig(**header['cfg'])
 sport=load_plugin(str(ROOT/'sports/tabletennis/plugin.py'));layer=sport.action_layer('high')
 issued=next(e for e in events if e['ev']=='model_issued' and e['seq']==a.seq)
 options=[o for o in issued['options'] if o['kind']=='act']
 results=[]
 for lead_ticks in ([15] if a.prep_step is not None else [15,25,40]):
  arrival=issued['k']+lead_ticks
  for option in options:
   for normal_only in ([False] if a.prep_step is not None else [False,True]):
    m=sport.build(cfg);timeline={}
    for e in events:
     if e.get('k',arrival)>=(a.prep_step if a.prep_step is not None else arrival):continue
     if e['ev'] in ['cmd','resume']:timeline.setdefault(e['k'],[]).append(e)
    replay_until=a.prep_step if a.prep_step is not None else arrival
    while m.k<replay_until:
     for e in timeline.get(m.k,[]):
      if e['ev']=='cmd':m.apply(e['seat'],e['cmd'])
      else:m.resume()
     m.step()
    prep_info=None
    if a.prep_step is not None:
     own=m.observe('A')
     assert own['ball_state']=='going to the opponent','Preparation requires an outgoing ball'
     prep={'type':'act','t':a.prep_duration,'pos':[0.,-1.1,.24],'normal':[0.,.85,.53],'vel':[0.,0.,0.],'base':[0.,-1.55]}
     parsed=parse_action(layer,'A',prep,m,{});low,prep_info=layer.lower('A',parsed,None,m);m.apply('A',low)
     while m.k<arrival and m.phase().state not in (UNIT_OVER,FINISHED):m.step()
    start_point=m.observe('A')['point'];body=dict(option['action']);body['t']=(option['contact_step']-m.k)*m.dt
    if normal_only:
     n=np.asarray(body['normal'],float);v=np.asarray(body['vel'],float);n=n/np.linalg.norm(n);body['vel']=(np.dot(v,n)*n).round(5).tolist()
    parsed=parse_action(layer,'A',body,m,{});low,info=layer.lower('A',parsed,None,m);m.apply('A',low)
    while m.k<arrival+400 and m.phase().state not in (UNIT_OVER,FINISHED):m.step()
    result={'seq':a.seq,'observation_step':issued['k'],'arrival_step':arrival,'candidate_id':option['id'],'normal_only':normal_only,'target_description':option['description'],'command':body,'before_point':start_point,'point_results':m.observe('A')['points'],'scores':m.scores(),'end_step':m.k,'scope':'native branch calibration, no GPT calls','prep_step':a.prep_step,'prep_duration':a.prep_duration if a.prep_step is not None else None,'prep_info':prep_info, 'stroke':{k:info.get(k) for k in ['T_from_now','blade_error_m','normal_error_deg','speed_scale','base','stroke']}}
    results.append(result);(a.output/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seq',type=int,default=59);p.add_argument('--prep-step',type=int);p.add_argument('--prep-duration',type=float,default=.6);run(p.parse_args())
