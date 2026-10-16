"""Event-driven simulation: subscription inference, measured virtual API delays."""
import asyncio,json,pathlib,random,time,heapq,hashlib,argparse
from .visual_env import VisualRhythmEnv
from .providers import NativeProvider
from .scheduler import ActionScheduler
from .policy import prompt,parse
ROOT=pathlib.Path(__file__).resolve().parents[2];RUNS=ROOT/'experiments/rhythm/runs'

async def episode(variant,seed,rows,*,cadence=.30,workers=3,capacity=8,latency_scale=1,round_name='r1',speed=1):
    out=RUNS/round_name/f'{variant}-seed{seed}';out.mkdir(parents=True,exist_ok=True)
    if (out/'summary.json').exists():return json.loads((out/'summary.json').read_text())
    rng=random.Random(seed);delays=[r['latency_s'] for r in rows];providers=[]
    try:
        for _ in range(workers):providers.append(await NativeProvider().start())
    except BaseException:
        await asyncio.gather(*(p.close() for p in providers),return_exceptions=True);raise
    scheduler=ActionScheduler();pending=[];seq=0;t=0.;next_obs=.45;calls=0;drops=0;errors=0;start=time.monotonic();hist=[];logs=[]
    async with VisualRhythmEnv('http://127.0.0.1:18891',virtual=True) as env:
        await env.start_virtual()
        try:
            while t<30:
                await env.advance(t);executed_now=scheduler.advance(t*1000);hist.extend({'time_s':a.game_ms/1000,'lane':a.lane} for a in executed_now)
                # Only answers whose sampled arrival time has been reached become visible.
                changed=False
                while pending and pending[0][0]<=t+1e-7:
                    due,rid,obs,future=heapq.heappop(pending)
                    try:
                        answer,meta=await future;actions=parse(answer,obs,variant)
                        accepted=scheduler.submit(str(rid),obs.time_s*1000,actions,t*1000,horizon_ms=1800,lanes=[0,1,2,3]);hist.extend({'time_s':a.game_ms/1000,'lane':a.lane} for a in accepted if a.game_ms<=t*1000)
                        log={'seq':rid,'obs_s':obs.time_s,'arrival_s':t,'sampled_delay_s':due-obs.time_s,'answer':answer,'actions':actions,'metadata':meta,'image_sha256':hashlib.sha256(obs.png).hexdigest()}
                        changed=True
                    except Exception as e:
                        errors+=1;log={'seq':rid,'obs_s':obs.time_s,'arrival_s':t,'error':type(e).__name__+': '+str(e)[:250]}
                    logs.append(log)
                    with (out/'decisions.jsonl').open('a') as f:f.write(json.dumps(log)+'\n')
                if changed:await env.replace_schedule([{'time':a.game_ms/1000,'lane':a.lane} for a in scheduler.pending()])
                if t+1e-7>=next_obs:
                    if len(pending)<capacity:
                        obs=await env.screenshot();(out/f'obs-{seq:04d}.png').write_bytes(obs.png)
                        text=prompt(obs,variant,delay_ms=[sorted(delays)[len(delays)//2]*1000,max(delays)*1000])
                        future=asyncio.create_task(providers[seq%workers].act(text,[obs.png]))
                        delay=rng.choice(delays)*latency_scale*speed
                        heapq.heappush(pending,(t+delay,seq,obs,future));seq+=1;calls+=1
                    else:drops+=1
                    next_obs+=cadence
                    if calls%10==0:
                        v=await env.evaluator();status={'round':round_name,'variant':variant,'seed':seed,'game_s':t,'calls':calls,'score':v['score'],'counts':v['counts'],'wall_s':time.monotonic()-start};(out/'progress.json').write_text(json.dumps(status));print('SIM_PROGRESS '+json.dumps(status),flush=True)
                candidates=[30.,next_obs]
                if pending:candidates.append(pending[0][0])
                future_actions=scheduler.pending()
                if future_actions:candidates.append(future_actions[0].game_ms/1000)
                t=min(x for x in candidates if x>t+1e-7)
            await env.advance(30);v=await env.evaluator()
            n=v['total_notes'];accuracy=v['score']/max(1,n*1000)
            summary={**v,'accuracy':accuracy,'variant':variant,'seed':seed,'calls':calls,'drops':drops,'errors':errors,'wall_s':time.monotonic()-start,'mode':'subscription_latency_simulation','speed':speed,'cadence_s':cadence,'real_workers':workers,'virtual_capacity':capacity,'latency_scale':latency_scale,'passed':accuracy>=.95 and v['counts']['miss']==0,'request_profile_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}
            (out/'summary.json').write_text(json.dumps(summary,indent=2));(out/'actions.json').write_text(json.dumps(await env.action_log()));print('SIM_COMPLETE '+json.dumps(summary),flush=True)
            return summary
        finally:
            for _,_,_,f in pending:f.cancel()
            await asyncio.gather(*(f for _,_,_,f in pending),return_exceptions=True)
            await asyncio.gather(*(p.close() for p in providers),return_exceptions=True)

async def main(args):
    data=json.loads((RUNS/'profile.json').read_text());rows=[r for r in data['rows'] if r['detail']=='high' and r.get('effort','low')==args.effort]
    if not rows:raise RuntimeError('No matched measured profile')
    semaphore=asyncio.Semaphore(args.episodes)
    async def job(v,s):
        async with semaphore:return await episode(v,s,rows,cadence=args.cadence,round_name=args.round,latency_scale=args.latency_scale,speed=args.speed,capacity=args.capacity)
    results=await asyncio.gather(*(job(v,s) for v in args.variants.split(',') for s in [2,5,6]))
    (RUNS/args.round/'summary.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',default='r1');p.add_argument('--variants',default='pixels_compact,pixels,pixels_future');p.add_argument('--episodes',type=int,default=8);p.add_argument('--cadence',type=float,default=.30);p.add_argument('--capacity',type=int,default=8);p.add_argument('--effort',default='low');p.add_argument('--latency-scale',type=float,default=1);p.add_argument('--speed',type=float,default=1);asyncio.run(main(p.parse_args()))
