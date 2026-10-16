"""Verify a development fork against native state and pixels; zero model calls."""
import argparse,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('MUJOCO_GL','egl')

def run(a):
    from core.episode import Episode,load_plugin,header_cfg
    from core.local import Views,_header,seat_spec
    from core import spec as spec_mod
    from rally_fork import setup
    cfg=header_cfg(json.loads((a.source/'episode.jsonl').read_text().splitlines()[0]))
    plugin=str(ROOT/'sports/tabletennis/plugin.py');sport=load_plugin(plugin)
    from candidates import Candidates
    m=sport.build(cfg);decl=spec_mod.load(plugin)
    views=Views(sport,cfg,m,decl,True,plugin)
    menu=Candidates(seat_spec(sport,cfg,'A',m=m,plugin=plugin),a.variant)
    profile=json.loads(a.profile.read_text())
    timing={'p50_wall_s':profile['p50_s'],'p95_wall_s':profile['p95_s'],'slowdown':cfg.slowdown,
            'p50_game_s':profile['p50_s']/cfg.slowdown,'p95_game_s':profile['p95_s']/cfg.slowdown,
            'observation_interval_game_s':.1,'virtual_model_capacity':8}
    a.output.mkdir(parents=True,exist_ok=False)
    ep=Episode(a.output/'episode.jsonl');_header(ep,sport,cfg)
    started=time.monotonic()
    result=setup(a.source,a.seq,m,views,menu,timing,ep)
    result.update(verified=True,wall_s=time.monotonic()-started,model_calls=0,api_spend_usd=0)
    (a.output/'verified_fork.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
    for renderer in sport.worker_call.__globals__.get('_LOCAL',{}).values():renderer.r.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--seq',type=int,required=True);p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--variant',default='geometry_stable_early_fast_feedback_executor_chunk')
    run(p.parse_args())
