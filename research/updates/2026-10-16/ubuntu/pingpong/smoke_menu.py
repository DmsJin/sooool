"""Fixed-choice servo smoke test; not a GPT performance result."""
import os
os.environ.setdefault('MUJOCO_GL','egl')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from pathlib import Path
import sys,json,argparse
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from core.episode import load_plugin,Episode
from core.local import Views,seat_spec,_header
from core import spec as spec_mod
from core.sport import MatchConfig,parse_action,UNIT_OVER,FINISHED

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    plugin=str(ROOT/'sports/tabletennis/plugin.py');s=load_plugin(plugin)
    from candidates import Candidates,menu_prompt
    cfg=MatchConfig(sport='tabletennis',format='match',seats=('A',),seed=2,level=1,slowdown=10)
    m=s.build(cfg);spec=seat_spec(s,cfg,'A',m=m,plugin=plugin);layer=s.action_layer('high');decl=spec_mod.load(plugin)
    viewmaker=Views(s,cfg,m,decl,True,plugin);menus=Candidates(spec);ep=Episode(a.output/'episode.jsonl');_header(ep,s,cfg)
    def effect(body):
        cmd=parse_action(layer,'A',body,m,{});low,info=layer.lower('A',cmd,None,m)
        ep.write('cmd',k=m.k,seat='A',cmd=low);m.apply('A',low)
        return info
    def capture(i):
        v=viewmaker.view('A',{'step':m.k,'t_sim':m.k*m.dt,'phase':'running','done':False})
        options=menus.build(v,{})
        sample={'view':v,'options':options,'prompt':menu_prompt(v,options,{'slowdown':10,'profile':'pending menu calibration'})}
        (a.output/f'sample_{i:03d}.json').write_text(json.dumps(sample));return options
    first=capture(0);effect(first[1]['action'])
    for _ in range(120):m.step()
    choices=capture(1)
    option=next(c for c in choices if c['kind']=='serve_bundle')
    infos=[]
    for item in option['actions']:
        due=120+item['after_steps']
        while m.k<due:m.step()
        infos.append(effect(item['action']))
    for _ in range(600):
        if m.phase().state in (UNIT_OVER,FINISHED):break
        m.step()
        if m.k%20==0:capture(m.k//20+2)
    ep.write('end',k=m.k,reason='one_point_smoke')
    result={'scope':'fixed-choice smoke, no GPT calls','scores':m.scores(),'k':m.k,'digest':m.state_digest(),
            'points':m.observe('A')['points'],'stroke_infos':infos}
    (a.output/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    for r in s.worker_call.__globals__.get('_LOCAL',{}).values():r.r.close()

if __name__=='__main__':main()
