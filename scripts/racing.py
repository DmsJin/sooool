"""Selected hybrid Racing checkpoint: causal subscription development and real API eval."""
from __future__ import annotations
import argparse,hashlib,json,math,os,pathlib,statistics,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
ENGINE=ROOT/'environments/racing'
sys.path.insert(0,str(ROOT))

from runtime.evaluation import recording
from runtime.options import credential, positive_float

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def evaluation_record(out,mode,returncode=0):
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
        'model_calls':{'simulate':'actual subscription','eval':'actual API','preflight':'none'}[mode],
        'hypothesis':manifest.get('hypothesis'),
        'limits':['hybrid coded visual tracking','Level 1 only','historical profile is proxy calibration, not exact current workload']}
    (out/'evaluation_record.json').write_text(json.dumps(record,indent=2));return record

def prepare(out,mode,recipe,hypothesis):
    if out.exists():raise ValueError('Output must be new; do not overwrite an evaluation')
    env=pathlib.Path(os.environ['RACING_ENV_ROOT'])
    return {'game':'racing','mode':mode,'recipe':recipe,'hypothesis':hypothesis,'environment_root':str(env.resolve()),'created_at_unix':time.time(),'selected_early_checkpoint':True}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.set_defaults(seed=None,summaries=False,max_calls=None,samples_dir=None)
    commands=p.add_subparsers(dest='mode',required=True)
    providers={'simulate':'subscription','eval':'api','profile':'api','preflight':'rules'}
    for mode,provider in providers.items():
        child=commands.add_parser(mode)
        child.add_argument('--output',type=pathlib.Path,required=True)
        child.add_argument('--provider',choices=[provider],default=provider,help=f'Decision source (default: {provider})')
        child.add_argument('--hypothesis',default='Replicate the frozen lane-commit checkpoint')
        if mode!='profile':
            child.add_argument('--seed',type=int)
        if mode in ('eval','profile'):
            child.add_argument('--ledger',type=pathlib.Path,required=True)
            child.add_argument('--stage-cap-usd',type=positive_float,required=True,help='Stage ceiling in USD')
        if mode=='eval':
            child.add_argument('--summaries',action='store_true',help='Same-response English summary then goal; separate video variant')
        if mode=='profile':
            child.add_argument('--max-calls',type=int,default=16)
            child.add_argument('--samples-dir',type=pathlib.Path)
    budget=commands.add_parser('budget')
    budget.add_argument('--ledger',type=pathlib.Path,required=True)
    budget.add_argument('--budget-usd',type=positive_float,required=True,help='Cumulative ledger ceiling in USD')
    a=p.parse_args(argv)
    if a.mode=='budget':
        a.ledger.parent.mkdir(parents=True,exist_ok=True)
        with a.ledger.open('x') as stream:
            json.dump({'limit_usd':a.budget_usd,'charged_upper_usd':0,'reserved':{},'stages':{}},stream,indent=2)
        return
    if not os.environ.get('RACING_ENV_ROOT'):
        p.error('Set RACING_ENV_ROOT to the read-only roboolympics checkout')
    if a.mode=='profile' and a.max_calls<1:
        p.error('--max-calls must be positive')
    if a.mode in ('eval','profile'):
        ledger=json.loads(a.ledger.read_text())
        if a.stage_cap_usd>ledger['limit_usd']:
            p.error('Stage cap exceeds ledger total cap')
    recipe=json.loads((ROOT/'recipes/racing.json').read_text())
    recipe['output_format']='public-summary-then-action' if a.summaries else 'action-only'
    if a.seed is not None:
        recipe['args']['seed']=a.seed
    out=a.output.resolve()
    manifest=prepare(out,a.mode,recipe,a.hypothesis)
    with recording(out,game='racing',command=a.mode,provider=a.provider,
                   clock='virtual' if a.mode=='simulate' else 'none' if a.mode=='profile' else 'wall',
                   result_file='profile.json' if a.mode=='profile' else 'summary.json',
                   detail_file=None if a.mode=='profile' else 'evaluation_record.json'):
        if a.mode=='profile':
            out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
            sys.path.insert(0,str(ENGINE))
            # Native/API adapters belong to the prepared game interpreter.
            from run import API,Budget,MINIMAL_SYSTEM,write,append
            from lane import parse_lane
            from explained_api import NEW_FORMAT,OLD_FORMAT
            samples=sorted((a.samples_dir or ROOT/'policies/racing/lane-commit-v14/example').rglob('input.json'))
            if not samples:
                raise ValueError('No recorded task inputs found')
            key=credential()
            client=API(key,Budget(a.ledger),stage='profile',cap=a.stage_cap_usd,instructions=MINIMAL_SYSTEM)
            rows=[]
            try:
                for i in range(a.max_calls):
                    path=samples[i%len(samples)]
                    inp=json.loads(path.read_text())
                    images=[image.read_bytes() for image in sorted(path.parent.glob('image_*.png'))]
                    if [hashlib.sha256(data).hexdigest() for data in images]!=inp['image_sha256']:
                        raise ValueError('Sample image hash mismatch')
                    prompt=inp['prompt'].replace(NEW_FORMAT,OLD_FORMAT)
                    answer,meta=client.act(prompt,images,out/f'call_{i:03d}',on_ready=lambda *_:None,validator=parse_lane)
                    parse_lane(answer)
                    rows.append(meta)
                    append(out/'measurements.jsonl',meta)
            finally:
                client.close()
                key=None
            values=sorted(row['published_seconds'] or row['wall_seconds'] for row in rows)
            write(out/'profile.json',{'n':len(rows),'concurrency':1,'timing':'validated action publication; streams fully drained serially',
                'min':min(values),'p50':statistics.median(values),'p95':values[math.ceil(.95*len(values))-1],
                'mean':statistics.mean(values),'delays':values,'separate_from_historical_profile':True})
            return
        driver='run.py' if a.mode=='simulate' else 'live_explained.py' if a.summaries else 'live.py'
        cmd=[sys.executable,str(ENGINE/driver)]
        if a.mode=='simulate':
            cmd+=['sim']
        cmd+=['--out',str(out),'--profile',str(ROOT/recipe['profile'])]
        for name,value in recipe['args'].items():
            if name=='workers' and a.mode!='simulate':
                continue
            cmd+=['--'+name,str(value)]
        if a.mode=='preflight':
            cmd+=['--executor-preflight']
        if a.mode=='eval':
            cmd+=['--budget',str(a.ledger.resolve()),'--validation-cap',str(a.stage_cap_usd)]
        env=dict(os.environ,MUJOCO_GL=os.environ.get('MUJOCO_GL','egl'),LP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
        # The native driver owns directory creation. Preserve the manifest even if it fails early.
        try:
            result=subprocess.run(cmd,env=env)
        finally:
            out.mkdir(parents=True,exist_ok=True)
            (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
        rec=evaluation_record(out,a.mode,result.returncode)
        print(json.dumps(rec,indent=2))
        if result.returncode:
            raise SystemExit(result.returncode)
        if rec['execution_integrity']!='verified':
            raise SystemExit('Evaluation did not pass integrity checks')


if __name__=='__main__':
    main()
