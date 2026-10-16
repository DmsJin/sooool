"""Trusted policy freeze and fresh held-out chart generation (never actor code)."""
import argparse,hashlib,json
from pathlib import Path
from .hidden_charts import generate
ROOT=Path(__file__).resolve().parents[2]
FILES=['dist/game.js','dist/model-executor.js','experiments/rhythm/model_env.py','experiments/rhythm/model_transport_env.py','experiments/rhythm/model_policy.py','experiments/rhythm/model_compact_policy.py','experiments/rhythm/model_lean_policy.py','experiments/rhythm/model_profile.py','experiments/rhythm/model_native.py','experiments/rhythm/providers.py','experiments/rhythm/model_image_budget.py','experiments/rhythm/model_token_preflight.py','experiments/rhythm/scheduler.py','experiments/rhythm/model_freeze.py','experiments/rhythm/hidden_charts.py']
def freeze(output,memory,private_dir,charts=3,*,cadence=.1,concurrency=20,max_output=256,image_token_certificate=None,max_miss=2,duration=30.000998):
 output=Path(output);output.mkdir(parents=True,exist_ok=False)
 manifest={'protocol':'literal-model-timing-v1','memory_sha256':hashlib.sha256(Path(memory).read_bytes()).hexdigest(),'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES},'runtime':{'cadence':cadence,'concurrency':concurrency,'frames':1,'detail':'high','max_output':max_output,'compact':True,'lean':True},'acceptance':{'duration_s':duration,'speed':1,'max_miss':max_miss,'episodes':charts}}
 if image_token_certificate:
  manifest['image_token_certificate_sha256']=hashlib.sha256(Path(image_token_certificate).read_bytes()).hexdigest()
 path=output/'freeze.json';path.write_text(json.dumps(manifest,indent=2))
 for name in FILES:
  snapshot=output/'source'/name;snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes((ROOT/name).read_bytes())
 heldouts=[]
 for _ in range(charts):
  chart=generate(private_dir,path,model_workspace=ROOT,duration=duration)
  heldouts.append({'chart_path':str(chart.chart_path),'public_metadata':chart.public_metadata()})
 (output/'trusted-heldouts.json').write_text(json.dumps(heldouts,indent=2));(output/'trusted-heldouts.json').chmod(0o600)
 print(json.dumps({'freeze':str(path),'charts':charts,'chart_hashes':[c['public_metadata']['chart_sha256'] for c in heldouts]}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--memory',required=True);p.add_argument('--private-dir',required=True);p.add_argument('--charts',type=int,default=3)
 p.add_argument('--max-miss',type=int,default=2);p.add_argument('--duration',type=float,default=30.000998)
 p.add_argument('--cadence',type=float,default=.1);p.add_argument('--concurrency',type=int,default=20);p.add_argument('--max-output',type=int,default=256);p.add_argument('--image-token-certificate')
 a=p.parse_args();freeze(a.output,a.memory,a.private_dir,a.charts,cadence=a.cadence,concurrency=a.concurrency,max_output=a.max_output,image_token_certificate=a.image_token_certificate,max_miss=a.max_miss,duration=a.duration)
