"""Counterfactual native API return diagnostic; no GPT or performance claim.
Only recorded permitted candidate actions are branched; the original command
history is replayed unchanged up to each branch's simulated decision arrival.
"""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MUJOCO_GL','egl')
from core.episode import load_plugin,header_cfg
from core.sport import parse_action,UNIT_OVER,FINISHED

def run(a):
 a.output.mkdir(parents=True,exist_ok=False)
 rows=[json.loads(l) for l in (a.source/'episode.jsonl').read_text().splitlines()]
 cfg=header_cfg(next(r for r in rows if r['ev']=='header'))
 sport=load_plugin(str(ROOT/'sports/tabletennis/plugin.py'));layer=sport.action_layer('high')
 results=[]
 for seq in a.seq:
  item=json.loads((a.source/'inputs'/f'{seq:05d}.json').read_text())
  recorded=json.loads(item['prompt'].split('\nSTATE ')[1].split('\nIMAGE_META ')[0])
  options=[None]+[o for o in item['options'] if o['kind']=='act']
  for option in options:
   m=sport.build(cfg);arrival=item['obs_step']+a.delay_ticks
   timeline={}
   for r in rows:
    if r['ev'] in ('cmd','resume') and r['k']<arrival:timeline.setdefault(r['k'],[]).append(r)
   while m.k<arrival:
    if m.k==item['obs_step']:
     state=m.observe('A')
     for key in ('q','point','score','heard','ball_state'):assert state[key]==recorded[key],(seq,key,m.k)
    for r in timeline.get(m.k,[]):
     if r['ev']=='cmd':m.apply(r['seat'],r['cmd'])
     else:m.resume()
    m.step()
   before=m.observe('A');info={}
   if option is not None:
    body=dict(option['action'],t=(option['contact_step']-arrival)*m.dt)
    assert body['t']>.04
    parsed=parse_action(layer,'A',body,m,{})
    low,info=layer.lower('A',parsed,None,m);m.apply('A',low)
   while m.k<arrival+400 and m.phase().state not in (UNIT_OVER,FINISHED):m.step()
   after=m.observe('A')
   result={'scope':'fixed native branch diagnostic; zero model calls','seq':seq,'observation_step':item['obs_step'],'arrival_step':arrival,'option':'keep_existing' if option is None else option['id'],'command_before':before.get('command'),'target':None if option is None else option['description'],'end_step':m.k,'point_results':after['points'],'scores':m.scores(),'shots':after.get('shots'),'stroke':{k:info.get(k) for k in ('T_from_now','blade_error_m','normal_error_deg','speed_scale','stroke')}}
   results.append(result);(a.output/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seq',type=int,nargs='+',default=[57,59]);p.add_argument('--delay-ticks',type=int,default=12);run(p.parse_args())
