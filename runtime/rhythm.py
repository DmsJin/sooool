"""Selected literal-time Rhythm policy: simulation, live API and serial profiling."""
import asyncio
import fcntl
import getpass
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
from types import SimpleNamespace


def modules(root):
    env=root/'environments/rhythm'
    sys.path.insert(0,str(env))
    return env


def ledger(root,out,a):
    modules(root)
    from experiments.rhythm.scheduler import BudgetLedger
    path=(a.ledger or out/'budget.json').resolve()
    book=BudgetLedger(path,str(a.budget_usd))
    with book._locked():pass
    before=book.snapshot()
    target=out/'budget.json'
    if path!=target.resolve():target.symlink_to(path)
    return book,before


def credential():
    key=os.environ.get('OPENAI_API_KEY') or getpass.getpass('OpenAI API key (process memory only): ')
    if not key:raise ValueError('A real API credential is required')
    return key


def simulate(root,recipe,out,a):
    env=modules(root)
    from experiments.rhythm.model_joint_training import run_episode
    from runtime.subscription import AsyncProvider
    from runtime.cli import serve
    kw=dict(recipe['args'])
    if a.duration is not None and a.duration!=kw['duration']:raise ValueError('Duration must match the selected chart; use a separate recipe/chart for ablations')
    if a.seed is not None:kw['seed']=a.seed
    with serve(env/'dist') as url:
        kw.update(url=url+'/?lang=en',run_root=str(out/'episodes'),browser_executable=a.browser_executable,
                  joint_profile=str(root/recipe['profile']),memory=str(root/recipe['memory']),chart=str(root/recipe['chart']))
        result=asyncio.run(run_episode(SimpleNamespace(**kw),provider_factory=AsyncProvider))
    (out/'summary.json').write_text(json.dumps(result,indent=2))
    return result


def evaluate(root,recipe,out,a):
    if a.seed is not None:raise ValueError('Native selected evaluation uses a fixed retained chart; --seed is for simulation')
    env=modules(root)
    from experiments.rhythm.model_native import run
    from runtime.cli import serve
    book,before=ledger(root,out,a)
    kw=dict(recipe['api'])
    if a.duration is not None and a.duration!=kw['duration']:raise ValueError('Duration must match the selected chart')
    source_hashes={str(p.relative_to(env)):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in env.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.css','.html','.woff') and '__pycache__' not in p.parts}
    frozen={'memory_sha256':hashlib.sha256((root/recipe['memory']).read_bytes()).hexdigest(),
            'source_sha256':source_hashes,'runtime':kw,'acceptance':{'duration_s':kw['duration'],'max_miss':0}}
    (out/'native-freeze.json').write_text(json.dumps(frozen,indent=2))
    key=credential()
    try:
        with serve(env/'dist') as url:
            kw.update(url=url+'/?lang=en',run_root=str(out),name='episode',freeze=str(out/'native-freeze.json'),
                      memory=str(root/recipe['memory']),chart=str(root/recipe['chart']),audio=str(a.audio or env/'dist/assets/preview-17s.m4a'),
                      browser_executable=a.browser_executable,max_calls=a.max_calls,
                      image_token_certificate=str(root/'profiles/rhythm/image-token-certificate.json'))
            asyncio.run(run(SimpleNamespace(**kw),key))
        result=json.loads((out/'model-timing/episode/result.json').read_text())
        (out/'summary.json').write_text(json.dumps(result,indent=2))
        return result
    finally:
        key=None
        report=accounting(out,before,book.snapshot())
        manifest=json.loads((out/'manifest.json').read_text())
        manifest['real_time_api_acceptance']=bool(locals().get('result',{}).get('passed') and report['all_settled'])
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2))


def accounting(out,before,after):
    entries={k:v for k,v in after['requests'].items() if k not in before['requests']}
    report={'calls':len(entries),'all_settled':all(v['state']=='settled' for v in entries.values()),
            'cost_usd':sum(v.get('actual_micros',0) for v in entries.values())/1e6,
            'committed_usd':after['committed_micros']/1e6,'remaining_usd':after['remaining_micros']/1e6,
            'old_uncertain_reservations_retained':True}
    (out/'accounting.json').write_text(json.dumps(report,indent=2))
    return report


def profile(root,a):
    """Sequentially replay retained public inputs; never execute an action."""
    from runtime.cli import freeze
    modules(root)
    from experiments.rhythm.providers import APIProvider
    from experiments.rhythm.model_lean_policy import parse
    recipe=json.loads((root/'recipes/rhythm.json').read_text())
    out=(a.output or root/'runs/rhythm-profile').resolve()
    freeze('rhythm',recipe,out,mode='serial_api_profile')
    book,before=ledger(root,out,a)
    source=a.episode.resolve()
    rows=sorted([json.loads(s) for s in (source/'requests.jsonl').read_text().splitlines()],key=lambda r:r['version'])
    if not rows:raise ValueError("No retained requests to profile")
    count=min(a.max_calls,len(rows))
    chosen=[rows[round(i*(len(rows)-1)/max(1,count-1))] for i in range(count)]
    key=credential()
    async def one():
        provider=APIProvider(key,out,phase='profiling',detail='high',max_output=512,
                             image_token_certificate=root/'profiles/rhythm/image-token-certificate.json')
        results=[]
        async def ready(answer,metadata):pass
        try:
            for row in chosen:
                answer,meta=await provider.act(row['prompt'],[(source/p).read_bytes() for p in row['frames']],
                    on_action=ready,action_validator=parse,live_commentary=True)
                results.append({'source_version':row['version'],'prompt':row['prompt'],'answer':answer,'metadata':meta})
                (out/'profile.json').write_text(json.dumps({'serial':True,'gameplay':False,'rows':results},indent=2))
        finally:await provider.close()
        values=[r['metadata']['action_ready_s'] for r in results]
        summary={'serial':True,'gameplay':False,'samples':len(values),'below_1p8':sum(x<1.8 for x in values),
                 'median_s':statistics.median(values),'sd_s':statistics.pstdev(values),'max_s':max(values)}
        (out/'summary.json').write_text(json.dumps(summary,indent=2))
        return summary
    # A shared ledger also shares its profiling lock, across output directories.
    lockpath=Path(str(a.ledger.resolve() if a.ledger else out/'budget.json')+'.profile.lock')
    try:
        with lockpath.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=asyncio.run(one())
        return result
    finally:
        key=None
        accounting(out,before,book.snapshot())
        from runtime.evaluation import record_run
        record_run(out)


def append_record(run,registry):
    """Idempotent append; a changed record under the same run ID is rejected."""
    run=Path(run);record=json.loads((run/'evaluation-record.json').read_text())
    if record['game']!='rhythm':raise ValueError('Expected a Rhythm evaluation record')
    if record.get('real_time_api_acceptance') and (record.get('mode')!='realtime_api' or not record.get('passed') or not (record.get('accounting') or {}).get('all_settled')):
        raise ValueError('Invalid real-time API acceptance claim')
    payload={'record_id':run.name,'record':record}
    registry=Path(registry);registry.parent.mkdir(parents=True,exist_ok=True)
    with registry.open('a+') as f:
        fcntl.flock(f,fcntl.LOCK_EX);f.seek(0)
        for line in f:
            old=json.loads(line)
            if old['record_id']==payload['record_id']:
                if old!=payload:raise ValueError('Changed evidence under an existing run ID')
                return False
        f.seek(0,2);f.write(json.dumps(payload,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
    return True
