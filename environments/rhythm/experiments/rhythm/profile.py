"""STRICTLY SERIAL target-workload profiling; key is supplied via hidden stdin."""
import asyncio,getpass,json,pathlib,statistics,time
from .visual_env import VisualRhythmEnv
from .providers import APIProvider
from .policy import prompt,parse
ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/rhythm/runs'
async def main(key):
    OUT.mkdir(exist_ok=True)
    provider=APIProvider(key,OUT);rows=json.loads((OUT/'profile-progress.json').read_text()) if (OUT/'profile-progress.json').exists() else []
    async with VisualRhythmEnv('http://127.0.0.1:18891',virtual=True) as env:
        await env.start_virtual()
        for index,t in enumerate([1.4,4.5,7.6,10.6,13.7,16.8,20.,23.2]):
            if index<len(rows):continue
            await env.advance(t);obs=await env.screenshot();(OUT/f'profile-{index:02d}.png').write_bytes(obs.png)
            detail='high';provider.detail=detail;provider.effort='low';provider.max_output=512
            text=prompt(obs,'pixels')
            # Await completion BEFORE issuing any next request. No parallel profiling.
            answer,meta=await provider.act(text,[obs.png]);valid=True
            try:events=parse(answer,obs,'pixels')
            except Exception:events=[];valid=False
            row={**meta,'index':index,'obs_game_s':obs.time_s,'geometry':obs.geometry,'answer':answer,'parsed':events,'valid':valid,'images':1}
            rows.append(row);(OUT/'profile-progress.json').write_text(json.dumps(rows,indent=2))
            print(json.dumps({'profile':index+1,'detail':detail,'latency_ms':round(meta['latency_s']*1000),'answer':answer,'cost_usd':meta['cost_usd']}),flush=True)
    await provider.close()
    groups={}
    for detail,effort in [('high','low'),('low','low')]:
        data=[r for r in rows if r['detail']==detail and r.get('effort','low')==effort];v=sorted(r['latency_s'] for r in data)
        if not v:continue
        groups[detail+'_'+effort]={'samples':len(v),'median_s':statistics.median(v),'p95_s':v[min(len(v)-1,int(.95*len(v)))],'min_s':min(v),'max_s':max(v),'valid':sum(r['valid'] for r in data)}
    result={'serial':True,'model':'gpt-6.1-sol','effort':'low','tier':'ultrafast','groups':groups,'rows':rows,'limitations':['Small sample tail estimates','Single request concurrency; concurrent API delays unmeasured','One-frame image input; new formats require recalibration']}
    (OUT/'profile.json').write_text(json.dumps(result,indent=2));print('PROFILE_DONE '+json.dumps(groups),flush=True)
if __name__=='__main__':
    key=getpass.getpass('API key (process memory only): ')
    asyncio.run(main(key))
