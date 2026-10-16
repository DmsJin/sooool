"""Fresh multi-seed policy comparison; existing simulator, shared eight native workers.

Only schedules model-controlled games. No game actions, targets or routes are
selected here. Native computation pauses each virtual game, as in simulate_5x.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import hashlib
import json
from pathlib import Path
import random
import sys
from simulate_5x import NativePool, base_prompt, run_episode, delay_frames


def main(args):
    if len(set(args.seeds)) != len(args.seeds) or len({p.stem for p in args.strategy}) != len(args.strategy):
        raise ValueError('Unique seeds and policy names required')
    delays=json.loads(args.profile.read_text())['capture_to_complete_seconds']
    for d in delays: delay_frames(d)
    schedule=[(p,seed,rep) for p in args.strategy for rep in range(args.repeats) for seed in args.seeds]
    random.Random(args.order_seed).shuffle(schedule)
    protocol={'model':'gpt-6.1-sol','reasoning_effort':'low','wrapper':'minimal',
        'controller':'HopControllerV3','virtual_raw_fps':12,'normal_game_fps':60,
        'max_native_workers':8,'virtual_workers_per_episode':8,'max_frames':args.max_frames,
        'repeats':args.repeats,'seeds':args.seeds,'episode_workers':3,'order_seed':args.order_seed,
        'latency_seed_offset':args.latency_seed_offset,'latency_scale':1.,
        'quota_stop_percent':args.quota_stop_percent,'paid_api_calls':0,
        'profile_sha256':hashlib.sha256(args.profile.read_bytes()).hexdigest(),
        'strategies':{p.stem:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.strategy},
        'episode_schedule':[{'policy':p.stem,'seed':seed,'repeat':rep} for p,seed,rep in schedule],
        'fresh_model_replies':True,'replay_prefix':None,
        'caveat':'historical measured API latency; no provider-failure model, candidate real API latency unmeasured. Exploratory comparison, no automatic policy promotion.'}
    if args.dry_run:
        print(json.dumps(protocol,indent=2));return
    sys.path.insert(0,str(args.source))
    args.output.mkdir(parents=True,exist_ok=False)
    sources=args.output/'source';sources.mkdir()
    protocol['source_sha256']={}
    for source in [Path(__file__)]+[Path(__file__).with_name(n) for n in ['simulate_5x.py','hop_controller_v2.py','hop_controller_v3.py','hop_controller_v4.py','case_subscription_client.py']]+[args.source/n for n in ['subscription_client.py','subscription_quota.py']]:
        data=source.read_bytes();(sources/source.name).write_bytes(data)
        protocol['source_sha256'][source.name]=hashlib.sha256(data).hexdigest()
    protocol['minimal_system_sha256']=hashlib.sha256(args.minimal_system_file.read_bytes()).hexdigest()
    (args.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    jobs=[]
    for path,seed,rep in schedule:
        cfg=copy.copy(args)
        cfg.output=args.output/path.stem/f'repeat-{rep}'
        cfg.output.mkdir(parents=True,exist_ok=True)
        cfg.strategy=path;cfg.controller='v3';cfg.latency_scale=1.;cfg.replay_root=None
        cfg.latency_seed_offset=args.latency_seed_offset+1000*rep
        prompt=base_prompt(path.read_text(),delays,1.,'v3')
        (cfg.output/'prompt.txt').write_text(prompt)
        config={**protocol,'strategy_sha256':protocol['strategies'][path.stem],
                'latency_seed_offset':cfg.latency_seed_offset,'virtual_raw_fps':12,
                'latency_scale':1.,'wrapper_profile':'minimal',
                'controller':'HopControllerV3: atomic hop, neutral landing, all commands require post-hop observation'}
        (cfg.output/'config.json').write_text(json.dumps(config,indent=2)+'\n')
        jobs.append((cfg,seed,rep,prompt,path.stem))
    results=[];pool=NativePool(args)
    try:
        with ThreadPoolExecutor(max_workers=3) as episodes:
            pending={episodes.submit(run_episode,cfg,seed,pool,prompt,delays):(policy,rep) for cfg,seed,rep,prompt,policy in jobs}
            for future in as_completed(pending):
                policy,rep=pending[future]
                result={**future.result(),'policy':policy,'repeat':rep}
                results.append(result)
                (args.output/'progress.json').write_text(json.dumps({'episodes':results,'planned':len(jobs)},indent=2)+'\n')
    finally:
        pool.close()
        for path in args.strategy:
            for rep in range(args.repeats):
                selected=[r for r in results if r['policy']==path.stem and r['repeat']==rep]
                (args.output/path.stem/f'repeat-{rep}'/'summary.json').write_text(json.dumps({'episodes':selected,'paid_api_calls':0},indent=2)+'\n')
        complete=len(results)==len(jobs) and all(not r.get('error') for r in results)
        (args.output/'summary.json').write_text(json.dumps({'status':'complete' if complete else 'incomplete','episodes':results,'paid_api_calls':0},indent=2)+'\n')
    if not complete: raise RuntimeError('Comparison incomplete; inspect actual episode errors, do not extrapolate scores')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','suite','profile','minimal-system-file','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--strategy',type=Path,nargs='+',required=True)
    p.add_argument('--seeds',type=int,nargs='+',default=[2,5,6])
    p.add_argument('--max-frames',type=int,choices=range(1,3601),default=1200)
    p.add_argument('--repeats',type=int,choices=[1,2],default=1)
    p.add_argument('--order-seed',type=int,default=20261016)
    p.add_argument('--latency-seed-offset',type=int,default=91)
    p.add_argument('--quota-stop-percent',type=int,choices=range(1,81),default=80)
    p.add_argument('--dry-run',action='store_true')
    main(p.parse_args())
