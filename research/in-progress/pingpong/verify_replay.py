"""Fresh native command replay and observed-state parity for a completed sim."""
import argparse,base64,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MUJOCO_GL','egl')
from core.episode import load_plugin
from core.sport import MatchConfig
from core.local import Views
from core import spec as spec_mod

def run(source,verify_images=False):
 expected=json.loads((source/'summary.json').read_text());assert expected['finished']
 events=[json.loads(line) for line in (source/'episode.jsonl').read_text().splitlines()]
 header=next(e for e in events if e['ev']=='header');cfg=MatchConfig(**header['cfg']);plugin=str(ROOT/'sports/tabletennis/plugin.py');sport=load_plugin(plugin);m=sport.build(cfg)
 views=Views(sport,cfg,m,spec_mod.load(plugin),True,plugin) if verify_images else None;images_verified=0
 timeline={};observed=0
 for e in events:
  if e['ev'] in ['cmd','resume','model_issued']:timeline.setdefault(e['k'],[]).append(e)
 while m.k<expected['k']:
  for e in timeline.get(m.k,[]):
   if e['ev']=='cmd':m.apply(e['seat'],e['cmd'])
   elif e['ev']=='resume':m.resume()
   else:
    text=json.loads((source/f"decision_{e['seq']:05d}/input.json").read_text())['params']['input'][0]['text']
    if '\nSTATE ' not in text:continue
    recorded=json.loads(text.split('\nSTATE ')[1].split('\nIMAGE_META ')[0]);state=m.observe('A')
    for key in ['q','point','score','heard','ball_state']:assert state[key]==recorded[key],(m.k,key,state[key],recorded[key])
    if views is not None:
     view=views.view('A',{'phase':'running','step':m.k,'t_sim':m.k*m.dt,'done':False})
     digest=hashlib.sha256(base64.b64decode(view['observation']['image_png_b64'])).hexdigest()
     assert digest==e['image_sha256'],('camera image mismatch',m.k,e['seq'],digest,e['image_sha256'])
     images_verified+=1
    observed+=1
  m.step()
 actual=m.state_digest();assert actual==expected['digest'],(actual,expected['digest'])
 report={'native_digest_exact_match':True,'digest':actual,'observations_verified':observed,'camera_pngs_verified':images_verified,'final_step':m.k,'scores':m.scores(),'fresh_native_process':True,'model_calls':0}
 for renderer in sport.worker_call.__globals__.get('_LOCAL',{}).values():renderer.r.close()
 (source/'verified_replay.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--verify-images',action='store_true');a=p.parse_args();run(a.source,a.verify_images)
