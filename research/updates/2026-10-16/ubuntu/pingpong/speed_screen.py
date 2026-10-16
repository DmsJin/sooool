"""Short subscription-only development batches; never acceptance evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

def run(a):
    from freeze import capture
    scripts=Path(__file__).resolve().parent
    a.output.mkdir(parents=True,exist_ok=False)
    previous=json.loads(a.external_manifest.read_text())
    manifest=capture(scripts,a.profile,scripts.parents[1],previous.get('external_hashes',{}))
    frozen=a.output/'freeze.json';frozen.write_text(json.dumps(manifest,indent=2))
    stages=[]
    variants=['geometry_stable_early_fast_feedback_executor_chunk',
              'geometry_stable_early_fast_feedback_executor_windup30_chunk']
    # Each larger batch is admitted only after the previous batch succeeds.
    for workers,gap,seeds in [(2,1,[151]),(4,.5,[103,107]),(8,.25,[109,113,127,131])]:
        plan={'scope':'Development screening only; partial games are not wins',
              'profile':str(a.profile),'freeze_manifest':str(frozen),
              'parallel_episodes':workers,'gap_s':gap,'delay_scale':1.25,
              'screen_points':2,'screen_decisions':30,
              'jobs':[{'name':f'{arm}-seed{seed}','seed':seed,'variant':variant}
                      for seed in seeds for arm,variant in zip(('control','windup30'),variants)]}
        plan_path=a.output/f'plan-{workers}.json';plan_path.write_text(json.dumps(plan,indent=2))
        out=a.output/f'batch-{workers}';started=time.monotonic()
        with (a.output/f'batch-{workers}.log').open('w') as log:
            code=subprocess.call([sys.executable,str(scripts/'run_round.py'),'--python',sys.executable,
                                  '--plan',str(plan_path),'--output',str(out)],stdout=log,stderr=subprocess.STDOUT)
        result=json.loads((out/'results.json').read_text()) if (out/'results.json').exists() else {}
        records=[]
        for path in out.glob('*/attempt_*/decision_*/result.json'):
            if not path.with_name('reused_from.json').exists():records.append(json.loads(path.read_text()))
        errors=[]
        for path in out.glob('*/attempt_*/native_*.stderr'):
            raw=path.read_text()
            if any(s in raw for s in ('serverOverloaded','Selected model is at capacity','429','TimeoutError')):
                errors.append(str(path))
        elapsed=time.monotonic()-started
        healthy=(code==0 and len(result.get('jobs',{}))==len(plan['jobs'])
                 and all(j['status'] in ('screened','complete') for j in result.get('jobs',{}).values())
                 and not errors and not any(r.get('subscription_retry_count',0) for r in records))
        stages.append({'workers':workers,'gap_s':gap,'wall_s':elapsed,'fresh_calls':len(records),
                       'calls_per_minute':len(records)*60/elapsed,'healthy':healthy,
                       'capacity_or_timeout_logs':errors,'results':str(out/'results.json')})
        (a.output/'throughput.json').write_text(json.dumps({'stages':stages,'api_spend_usd':0,
            'acceptance':False,'note':'Concurrency changes measured executor contention; compare policies within each batch.'},indent=2))
        print(json.dumps(stages[-1]),flush=True)
        if not healthy:break

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--external-manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
