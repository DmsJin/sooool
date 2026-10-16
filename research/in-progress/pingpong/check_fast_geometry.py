"""Numeric parity and timing check; not a game-performance evaluation."""
import json,sys,time,base64
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from core.episode import load_plugin
load_plugin(str(ROOT/'sports/tabletennis/plugin.py'))
import builtin_players as public
from fast_geometry import install
from candidates import Candidates

def main():
 original,fast=install();rng=np.random.default_rng(815);maximum=0.;samples=[]
 for i in range(200):
  p=rng.uniform([-1.,-1.8,.01],[1.,1.8,1.2]);v=rng.uniform([-4.,-7.,-4.],[4.,7.,4.]);dt=float(rng.choice([.001,.002,.005,.01]));n=int(rng.integers(1,600));ae=rng.uniform(-2.,2.,3) if i%3==0 else None;args=(p,v,dt,n,bool(i%2),ae)
  expected=original(*args);actual=fast(*args)
  assert expected[2]==actual[2],('bounce mismatch',i)
  for e,a in zip(expected[:2],actual[:2]):
   error=float(np.max(np.abs(e-a)));maximum=max(maximum,error);assert np.allclose(e,a,rtol=0,atol=1e-11),(i,error)
  samples.append(args)
 timings={}
 for name,fn in [('original',original),('fast',fast)]:
  before=time.monotonic()
  for args in samples:fn(*args)
  timings[name]=time.monotonic()-before
 base=Path('/home/ubuntu/wzh/sooool-runtime');src=base/'stable-single-seed2';spec=json.loads((base/'preflight/spec.json').read_text());menus={};menu_times={}
 for name,fn in [('original',original),('fast',fast)]:
  public.rollout=fn;c=Candidates(spec,mode='geometry_stable_early_chunk');out=[];before=time.monotonic()
  for seq in range(55,66):
   text=json.loads((src/f'decision_{seq:05d}/input.json').read_text())['params']['input'][0]['text'];state=json.loads(text.split('\nSTATE ')[1].split('\nIMAGE_META ')[0]);meta=json.loads(text.split('\nIMAGE_META ')[1].split('\nCANDIDATES ')[0]);timing=json.loads(text.split('\nTIMING ')[1].split('\nSTATE ')[0]);meta['image_png_b64']=base64.b64encode((src/'observations'/f'{seq:05d}.png').read_bytes()).decode();out.append(c.build({'state':state,'observation':meta},timing))
  menus[name]=out;menu_times[name]=time.monotonic()-before
 assert menus['original']==menus['fast'],'Full candidate JSON mismatch'
 result={'random_trajectories':200,'max_abs_error':maximum,'trajectory_timing_s':timings,'candidate_observations':11,'candidate_json_exact_match':True,'candidate_timing_s':menu_times,'native_physics_modified':False,'model_calls':0}
 (base/'fast-geometry-check.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':main()
