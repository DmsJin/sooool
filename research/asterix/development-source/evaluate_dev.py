"""Frozen three-seed rounds; bounded recovery preserves incomplete results."""
import argparse, concurrent.futures, hashlib, json, math, os, pathlib, subprocess, sys, time
from simulate_async import INTERCEPT_CANDIDATES
SEEDS=(2,5,6)
VARIANTS=tuple(dict.fromkeys(('lanes_guard','guard_pipeline','guard_intercept','guard_spaced',*INTERCEPT_CANDIDATES)))

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--output',type=pathlib.Path,required=True)
 p.add_argument('--suite',type=pathlib.Path,required=True)
 p.add_argument('--profile',type=pathlib.Path,required=True)
 p.add_argument('--resume',action='store_true')
 p.add_argument('--retry-incomplete',action='store_true')
 p.add_argument('--extra-attempts',type=int,choices=(0,1),default=0)
 p.add_argument('--episode-workers',type=int,choices=(1,2,3),default=3)
 p.add_argument('--native-workers',type=int,choices=(1,2,3),default=3)
 p.add_argument('--variants',nargs='+',choices=VARIANTS,default=list(VARIANTS[:3]))
 p.add_argument('--quota-stop-percent',type=int,choices=range(1,100))
 p.add_argument('--screen-only',action='store_true')
 p.add_argument('--latency-scale',type=float,default=1.)
 a=p.parse_args()
 if len(set(a.variants))!=len(a.variants):p.error('variants must be unique')
 if not math.isfinite(a.latency_scale) or a.latency_scale<1:p.error('latency-scale must be finite and >=1')
 a.output.mkdir(parents=True,exist_ok=a.resume)
 source=pathlib.Path(__file__).parent
 snapshot=a.output/'source';snapshot.mkdir(exist_ok=a.resume)
 for name in ('simulate_async.py','simulate.py','subscription_client.py','subscription_quota.py','chunk_control.py','evaluate_dev.py'):
  if not (snapshot/name).exists():(snapshot/name).write_bytes((source/name).read_bytes())
 state={'status':'running','variants':a.variants,'dev_seeds':SEEDS,'held_out_seeds':[7,8,9],'max_game_seconds':60,'speed_fraction':0.125,'virtual_capacity':8,'target_mean':1500,'api_spend_usd':0,'rounds':[], 'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.glob('*.py')}}
 if a.resume:
  previous=json.loads((a.output/'status.json').read_text());state['rounds']=[r for r in previous.get('rounds',[]) if not (a.retry_incomplete and r.get('errors'))]
  if previous.get('variants',list(VARIANTS[:3]))!=a.variants:raise ValueError('Cannot change variants in a frozen evaluation')
 state['recovery_controls']={'extra_attempts':a.extra_attempts,'episode_workers':a.episode_workers,'native_workers':a.native_workers,'retry_incomplete':a.retry_incomplete}
 state['quota_stop_percent']=a.quota_stop_percent
 state['latency_scale']=a.latency_scale
 def save():
  tmp=a.output/'status.tmp';tmp.write_text(json.dumps(state,indent=2));tmp.replace(a.output/'status.json')
 def episode(variant,seed,label,scale):
  prefix=None
  for attempt in range(3+a.extra_attempts):
   suffix='' if attempt==0 else f'-retry{attempt}'
   out=a.output/f'{label}-seed{seed}{suffix}'
   if out.exists():
    # Adopt a still-running episode after an orchestrator restart.
    while True:
     active=False
     for proc in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
      try:args=proc.read_bytes().split(b'\0')
      except OSError:continue
      if str(out).encode() in args and any(x.endswith(b'/simulate_async.py') for x in args):active=True;break
     if not active:break
     time.sleep(2)
   else:
    cmd=[sys.executable,str(snapshot/'simulate_async.py'),'--suite',str(a.suite),'--profile',str(a.profile),'--output',str(out),'--seed',str(seed),'--variants',variant,'--max-frames','3600','--native-workers',str(a.native_workers),'--latency-scale',str(scale)]
    if prefix:cmd+=['--replay-prefix',str(prefix)]
    if a.quota_stop_percent is not None:cmd+=['--quota-stop-percent',str(a.quota_stop_percent)]
    with (a.output/f'{label}-seed{seed}{suffix}.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=False)
   if (out/variant/'summary.json').exists():break
   failure=json.loads((out/'failure.json').read_text()) if (out/'failure.json').exists() else {}
   prefix=out/variant/'completed_prefix.jsonl'
   transient=failure.get('type')=='TimeoutError' or (failure.get('type')=='RuntimeError' and 'serverOverloaded' in failure.get('error',''))
   if not transient or not prefix.exists() or attempt==2+a.extra_attempts:
    error=RuntimeError(f'Episode did not complete: {out}; {failure}');error.transient_exhausted=transient
    raise error
  result=json.loads((out/variant/'summary.json').read_text())
  rows=[json.loads(x) for x in (out/variant/'decisions.jsonl').read_text().splitlines()]
  usages=[r.get('token_usage',{}).get('last',{}) for r in rows]
  result['average_tokens']={k:sum(x.get(k,0) for x in usages)/len(usages) for k in ('inputTokens','outputTokens','reasoningOutputTokens')}
  result['result_directory']=str(out/variant)
  return result
 def round_(variant,label,scale=1):
  existing=next((r for r in state['rounds'] if r['label']==label),None)
  if existing:return existing
  state['active_round']=label;save()
  results=[];errors=[]
  with concurrent.futures.ThreadPoolExecutor(max_workers=a.episode_workers) as pool:
   futures={pool.submit(episode,variant,seed,label,scale):seed for seed in SEEDS}
   for future in concurrent.futures.as_completed(futures):
    try:results.append(future.result())
    except RuntimeError as exc:
     if not getattr(exc,'transient_exhausted',False):raise
     errors.append({'seed':futures[future],'error':str(exc)})
     state['active_errors']=errors;save()
  results.sort(key=lambda r:r['seed'])
  complete=len(results)==3 and not errors
  row={'label':label,'variant':variant,'latency_scale':scale,'episodes':results,'errors':errors,'mean_score':sum(x['score'] for x in results)/3 if complete else None,'min_score':min(x['score'] for x in results) if complete else None}
  state.pop('active_errors',None)
  state['rounds'].append(row);save();print(json.dumps(row),flush=True);return row
 try:
  for variant in a.variants:round_(variant,variant,a.latency_scale)
  best=max((r for r in state['rounds'] if r['label'] in a.variants and r['mean_score'] is not None),key=lambda r:r['mean_score'],default=None)
  state['selected_variant']=best['variant'] if best else None
  if best and best['mean_score']>=1500 and not a.screen_only:
   repeat=round_(best['variant'],'confirmation')
   state['repeated_dev_target_met']=repeat['mean_score'] is not None and repeat['mean_score']>=1500
   round_(best['variant'],'latency125',1.25)
  else:state['repeated_dev_target_met']=False
  state['status']='complete_with_failures' if any(r.get('errors') for r in state['rounds']) else 'complete';state.pop('active_round',None);save()
 except BaseException as exc:
  state['status']='failed';state['error']=repr(exc);save();raise
if __name__=='__main__':main()
