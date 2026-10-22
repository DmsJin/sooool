"""Selected hybrid Racing checkpoint: causal subscription development and real API eval."""
from __future__ import annotations
import argparse,hashlib,json,math,os,pathlib,statistics,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
ENGINE=ROOT/'environments/racing'

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def record_run(out,mode,recipe,returncode=0):
    summary=json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else {}
    final_path=out/'service/final.json';final=json.loads(final_path.read_text()) if final_path.exists() else {}
    manifest=json.loads((out/'manifest.json').read_text())
    recipe=manifest['recipe']
    replay_path=out/('replay_check.json' if mode=='simulate' else 'service/replay_check.json')
    replay=json.loads(replay_path.read_text()) if replay_path.exists() else {}
    expected_sha=summary.get('digest') if mode=='simulate' else final.get('state_sha')
    replay_ok=bool(expected_sha) and replay.get('state_sha')==expected_sha
    integrity=(replay_ok and returncode==0 and summary.get('status')=='complete' and (summary.get('replay_matches') is True if mode=='simulate' else final.get('valid_trial') is True and final.get('deterministic') is True))
    if mode=='eval':
        model_ok=(summary.get('driver')!='camera-reference-executor-preflight-NOT-GPT' and summary.get('service_tier')=='ultrafast' and summary.get('model')=='gpt-6.1-sol' and summary.get('artificial_delay') is False and final.get('player_modes',{}).get('A')=='model')
        packets=list(out.glob('decision_*/result.json'))
        model_ok=model_ok and len(packets)==summary.get('calls') and len(packets)>0
        for f in packets:
            r=json.loads(f.read_text());ip=f.with_name('input.json')
            if not ip.exists():model_ok=False;continue
            inp=json.loads(ip.read_text());images=sorted(f.parent.glob('image_*.png'))
            model_ok=model_ok and r.get('model')=='gpt-6.1-sol' and r.get('service_tier')=='ultrafast' and bool(images) and [digest(x) for x in images]==inp.get('image_sha256')
        integrity=integrity and model_ok
    elif mode=='simulate':integrity=integrity and summary.get('auth')=='chatgpt'
    else:integrity=integrity and summary.get('driver')=='camera-reference-executor-preflight-NOT-GPT'
    record={'schema_version' :1,'policy':recipe['policy'],'mode':mode,'real_time_api_acceptance':mode=='eval' and integrity,
        'execution_integrity':'verified' if integrity else 'incomplete_or_unverified','process_returncode':returncode,
        'won':summary.get('won') if integrity else None,'summary':summary,'canonical_final':str(final_path.relative_to(out)) if final else None,'replay_hash_matches':replay_ok,
        'recipe_sha256':hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest(),'profile_sha256':digest(ROOT/recipe['profile']),
        'model_calls':{'simulate':'actual subscription','eval':'actual API','preflight':'none'}[mode],
        'hypothesis':manifest.get('hypothesis'),
        'limits':['hybrid coded visual tracking','Level 1 only','historical profile is proxy calibration, not exact current workload']}
    (out/'evaluation_record.json').write_text(json.dumps(record,indent=2));return record

def prepare(out,mode,recipe,hypothesis):
    if out.exists():raise ValueError('Output must be new; do not overwrite an evaluation')
    files={}
    for base in [ENGINE,ROOT/'policies/racing',ROOT/'profiles/racing',ROOT/'recipes/racing.json',ROOT/'runtime/cli.py',ROOT/'runtime/envs.py',
                 ROOT/'environments/registry.json',pathlib.Path(__file__)]:
        for p in ([base] if base.is_file() else sorted(base.rglob('*'))):
            if p.is_file() and '__pycache__' not in p.parts:
                rel=p.relative_to(ROOT);files[str(rel)]=digest(p)
    env=pathlib.Path(os.environ['RACING_ENV_ROOT']);envfiles={}
    for base in [env/'core',env/'sports/racing',env/'players/metering']:
        for p in sorted(base.rglob('*')):
            if p.is_file() and p.suffix in ('.py','.toml','.xml','.json') and '__pycache__' not in p.parts:envfiles[str(p.relative_to(env))]=digest(p)
    return {'game':'racing','mode':mode,'recipe':recipe,'hypothesis':hypothesis,'source_sha256':files,'environment_source_sha256':envfiles,'environment_root':str(env.resolve()),'created_at_unix':time.time(),'selected_early_checkpoint':True}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['simulate','eval','profile','preflight','record','budget'])
    p.add_argument('--output',type=pathlib.Path);p.add_argument('--seed',type=int);p.add_argument('--hypothesis',default='Replicate the frozen lane-commit checkpoint')
    p.add_argument('--budget-ledger',type=pathlib.Path);p.add_argument('--total-cap-usd',type=float);p.add_argument('--stage-cap-usd',type=float)
    p.add_argument('--summaries',action='store_true',help='Same-response English summary then goal; separate video variant')
    p.add_argument('--calls',type=int,default=16);p.add_argument('--samples-dir',type=pathlib.Path);p.add_argument('--record-mode',choices=['simulate','eval','preflight'],default='eval')
    a=p.parse_args(argv);recipe=json.loads((ROOT/'recipes/racing.json').read_text())
    if a.mode=='budget':
        if a.budget_ledger is None or a.total_cap_usd is None or not math.isfinite(a.total_cap_usd) or a.total_cap_usd<=0:p.error('budget requires --budget-ledger and positive --total-cap-usd')
        a.budget_ledger.parent.mkdir(parents=True,exist_ok=True)
        with a.budget_ledger.open('x') as f:json.dump({'limit_usd':a.total_cap_usd,'charged_upper_usd':0,'reserved':{},'stages':{}},f,indent=2)
        return
    if a.output is None:p.error('--output is required')
    out=a.output.resolve()
    if a.mode=='record':print(json.dumps(record_run(out,a.record_mode,recipe),indent=2));return
    if not os.environ.get('RACING_ENV_ROOT'):p.error('Set RACING_ENV_ROOT to the read-only roboolympics checkout')
    if a.summaries and a.mode!='eval':p.error('--summaries is an API video variant; use eval')
    if a.mode in ('eval','profile'):
        if a.budget_ledger is None or a.stage_cap_usd is None or not math.isfinite(a.stage_cap_usd) or a.stage_cap_usd<=0:p.error('paid modes require an existing --budget-ledger and positive --stage-cap-usd')
        ledger=json.loads(a.budget_ledger.read_text())
        if a.stage_cap_usd>ledger['limit_usd']:p.error('stage cap exceeds ledger total cap')
    recipe['output_format']='public-summary-then-action' if a.summaries else 'action-only'
    if a.seed is not None:recipe['args']['seed']=a.seed
    manifest=prepare(out,a.mode,recipe,a.hypothesis)
    if a.mode=='profile':
        if a.calls<1:p.error('--calls must be positive')
        out.mkdir();(out/'manifest.json').write_text(json.dumps(manifest,indent=2));sys.path.insert(0,str(ENGINE))
        from run import API,Budget,MINIMAL_SYSTEM,write,append
        from lane import parse_lane
        import getpass
        samples=sorted((a.samples_dir or ROOT/'policies/racing/lane-commit-v14/example').rglob('input.json'))
        if not samples:raise ValueError('No recorded task inputs found')
        # Serial, including SSE drain and accounting; no background actors launched here.
        client=API(getpass.getpass('API credential (memory only): '),Budget(a.budget_ledger),stage='profile',cap=a.stage_cap_usd,instructions=MINIMAL_SYSTEM);rows=[]
        try:
            for i in range(a.calls):
                f=samples[i%len(samples)];inp=json.loads(f.read_text());images=[x.read_bytes() for x in sorted(f.parent.glob('image_*.png'))]
                if [hashlib.sha256(b).hexdigest() for b in images]!=inp['image_sha256']:raise ValueError('Sample image hash mismatch')
                # Remove only the video output wrapper when profiling the action-only policy.
                from explained_api import NEW_FORMAT,OLD_FORMAT
                prompt=inp['prompt'].replace(NEW_FORMAT,OLD_FORMAT)
                answer,meta=client.act(prompt,images,out/f'call_{i:03d}',on_ready=lambda *_:None,validator=parse_lane)
                parse_lane(answer);rows.append(meta);append(out/'measurements.jsonl',meta)
        finally:client.close()
        values=sorted(r['published_seconds'] or r['wall_seconds'] for r in rows)
        write(out/'profile.json',{'n':len(rows),'concurrency':1,'timing':'validated action publication; streams fully drained serially','min':min(values),'p50':statistics.median(values),'p95':values[math.ceil(.95*len(values))-1],'mean':statistics.mean(values),'delays':values,'separate_from_historical_profile':True});return
    kw=recipe['args'];cmd=[sys.executable,str(ENGINE/('run.py' if a.mode=='simulate' else 'live_explained.py' if a.summaries else 'live.py'))]
    if a.mode=='simulate':cmd+=['sim']
    cmd+=['--out',str(out),'--profile',str(ROOT/recipe['profile'])]
    for k,v in kw.items():
        if k=='workers' and a.mode!='simulate':continue
        cmd+=['--'+k,str(v)]
    if a.mode=='preflight':cmd+=['--executor-preflight']
    if a.mode=='eval':cmd+=['--budget',str(a.budget_ledger.resolve()),'--validation-cap',str(a.stage_cap_usd)]
    env=dict(os.environ,MUJOCO_GL=os.environ.get('MUJOCO_GL','egl'),LP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    # A manifest adjacent to the output survives failure before the driver creates it.
    out.parent.mkdir(parents=True,exist_ok=True);pending=out.with_name(out.name+'.manifest.json');pending.write_text(json.dumps(manifest,indent=2))
    result=subprocess.run(cmd,env=env)
    out.mkdir(exist_ok=True);(out/'manifest.json').write_bytes(pending.read_bytes());pending.unlink()
    rec=record_run(out,a.mode,recipe,result.returncode);print(json.dumps(rec,indent=2))
    if result.returncode:raise SystemExit(result.returncode)
    if rec['execution_integrity']!='verified':raise SystemExit('Evaluation did not pass integrity checks')
if __name__=='__main__':main()
