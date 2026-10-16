"""Fresh native command replay and observed-state parity for a completed sim."""
import argparse,base64,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MUJOCO_GL','egl')
from core.episode import load_plugin
from core.sport import MatchConfig
from core.local import Views
from core import spec as spec_mod

def recorded_state(text,direct=False):
 if '\nSTATE ' not in text:
  if direct:raise ValueError('Direct decision is missing public STATE evidence')
  return None
 return json.loads(text.split('\nSTATE ',1)[1].split('\nIMAGE_META ',1)[0])

def run(source,verify_images=False,allow_screened=False):
 expected=json.loads((source/'summary.json').read_text());direct=expected.get('variant','').startswith('direct_')
 partial=not expected['finished']
 assert expected['finished'] or (allow_screened and direct and expected.get('screened') and not expected.get('failure'))
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
    recorded=recorded_state(text,direct)
    if recorded is None:continue
    if direct:assert (source/'observations'/f"{e['seq']:05d}.prompt.txt").read_text()==text,('direct prompt mismatch',e['seq'])
    state=m.observe('A')
    for key in ['q','point','score','heard','ball_state']:assert state[key]==recorded[key],(m.k,key,state[key],recorded[key])
    if views is not None:
     view=views.view('A',{'phase':'running','step':m.k,'t_sim':m.k*m.dt,'done':False})
     digest=hashlib.sha256(base64.b64decode(view['observation']['image_png_b64'])).hexdigest()
     assert digest==e['image_sha256'],('camera image mismatch',m.k,e['seq'],digest,e['image_sha256'])
     images_verified+=1
    observed+=1
  m.step()
 actual=m.state_digest();assert actual==expected['digest'],(actual,expected['digest'])
 if direct:
  assert observed==expected['calls'],('missing direct state checks',observed,expected['calls'])
  if verify_images:assert images_verified==expected['calls'],('missing direct image checks',images_verified,expected['calls'])
 report={'native_digest_exact_match':True,'digest':actual,'observations_verified':observed,'camera_pngs_verified':images_verified,'final_step':m.k,'scores':m.scores(),'fresh_native_process':True,'model_calls':0}
 if partial:report.update(partial_screened=True,acceptance=False,scope='Direct development screen only; not fullgame wins')
 for renderer in sport.worker_call.__globals__.get('_LOCAL',{}).values():renderer.r.close()
 (source/('verified_screened_replay.json' if partial else 'verified_replay.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--verify-images',action='store_true');p.add_argument('--allow-screened',action='store_true');a=p.parse_args();run(a.source,a.verify_images,a.allow_screened)
