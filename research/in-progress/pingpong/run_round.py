"""Bounded subscription rounds with causal recovery and complete-only scoring."""
import argparse,concurrent.futures as cf,json,os,subprocess,sys,time
from pathlib import Path

def run(a):
 plan=json.loads(a.plan.read_text());a.output.mkdir(parents=True,exist_ok=False)
 (a.output/'plan.json').write_text(json.dumps(plan,indent=2));results={}
 manifest=json.loads(Path(plan['freeze_manifest']).read_text()) if plan.get('freeze_manifest') else None
 def frozen():
  if manifest is not None:
   from freeze import verify
   verify(manifest,Path(__file__).parent,plan['profile'])
 if manifest is not None:
  frozen();(a.output/'freeze_manifest.json').write_text(json.dumps(manifest,indent=2))
 def job(cfg):
  name=cfg['name'];root=a.output/name;root.mkdir();source=cfg.get('resume_from');attempts=[]
  for attempt in range(3):
   out=root/f'attempt_{attempt:02d}'
   try:frozen()
   except (ValueError,OSError) as exc:return name,{'status':'incomplete','failure':str(exc),'include_in_scores':False}
   cmd=[a.python,str(Path(__file__).with_name('simulate.py')),'--output',str(out),'--profile',plan['profile'],'--seed',str(cfg['seed']),'--variant',cfg['variant'],'--workers','1','--delay-scale',str(plan.get('delay_scale',1))]
   if source:cmd+=['--resume-from',str(source)]
   with (root/f'attempt_{attempt:02d}.log').open('w') as log:
    p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'MUJOCO_GL':'egl','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','SOOOOL_SUBSCRIPTION_GAP_S':str(plan.get('gap_s',6))})
    (root/'active_process.json').write_text(json.dumps({'pid':p.pid,'attempt':attempt,'output':str(out)}));code=p.wait()
   try:
    frozen()
    if manifest is not None:
     actual=json.loads((out/'protocol.json').read_text())
     if actual['source_hashes']!=manifest['source_hashes'] or actual['profile_sha256']!=manifest['profile_sha256']:
      raise ValueError('Episode snapshot differs from frozen manifest')
   except (ValueError,OSError,KeyError) as exc:return name,{'status':'incomplete','failure':str(exc),'include_in_scores':False,'output':str(out)}
   summary=json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else {'finished':False,'failure':'no summary'}
   attempts.append({'output':str(out),'exit_code':code,'summary':summary});(root/'attempts.json').write_text(json.dumps(attempts,indent=2))
   if code==0 and summary.get('finished'):return name,{'status':'complete','summary':summary,'output':str(out),'attempts':len(attempts)}
   stderr='\n'.join(p.read_text()[-6000:] for p in out.glob('native_*.stderr'))
   # Never retry numerical replay mismatches, quota exhaustion, or changed model.
   overload='serverOverloaded' in stderr or 'Selected model is at capacity' in stderr
   if not overload or attempt==2:return name,{'status':'incomplete','attempts':attempts,'include_in_scores':False}
   source=out;time.sleep(60)
 with cf.ThreadPoolExecutor(max_workers=plan.get('parallel_episodes',2)) as pool:
  futures=[pool.submit(job,j) for j in plan['jobs']]
  for future in cf.as_completed(futures):
   name,result=future.result();results[name]=result
   complete=[r['summary'] for r in results.values() if r['status']=='complete']
   report={'jobs':results,'completed':len(complete),'wins':sum(r['winner']=='A' for r in complete),'api_spend_usd':0,'incomplete_excluded':True}
   (a.output/'results.json').write_text(json.dumps(report,indent=2));print(name,json.dumps(result),flush=True)
 print('ROUND_TERMINAL',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--python',default='/home/ubuntu/wzh/sooool-runtime/venv/bin/python');run(p.parse_args())
