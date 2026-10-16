"""Trusted environment checks, not policy input. Run with local dist server18891."""
import asyncio
import json
from pathlib import Path
from experiments.rhythm.visual_env import VisualRhythmEnv, ROOT

async def check(url='http://127.0.0.1:18891'):
    async with VisualRhythmEnv(url, virtual=True) as env:
        initial=await env.start_virtual()
        assert initial.png.startswith(b'\x89PNG\r\n\x1a\n')
        assert set(initial.policy_metadata()) == {'time_s','capture_start_s','capture_end_s','geometry','state'}
        assert initial.geometry['hitline_y'] == 601
        # Chart is an EVALUATOR oracle, never passed to model/workers.
        chart=json.loads((ROOT/'dist/chart.json').read_text())
        actions=[{'time':n['time'],'lane':n['lane']} for n in chart['notes']]
        await env.schedule([{'time':.25,'lane':3}])
        await env.replace_schedule(actions)
        await env.advance(10)
        assert not any(a['time']==.25 for a in await env.action_log())
        remaining=[a for a in actions if a['time']>10]
        await env.replace_schedule(remaining)
        await env.advance(chart['duration']+.01)
        outcome=await env.evaluator()
        assert outcome['state']=='result', outcome
        assert outcome['counts']=={'perfect':len(actions),'great':0,'ok':0,'miss':0},outcome
        assert outcome['empty_presses']==0,outcome
        log=await env.action_log()
        assert len(log)==len(actions),len(log)
        assert all(a['status']=='executed' and abs(a['actual']-a['time'])<1e-6 for a in log)
        await env.schedule([{'time':1.,'lane':0}])
        assert (await env.action_log())[-1]['status']=='expired'
        try: await env.advance(1)
        except Exception: pass
        else: raise AssertionError('Clock rewind accepted')
        print(json.dumps({'test':'visual_env_oracle','outcome':outcome,'actions':len(log)}),flush=True)

if __name__=='__main__': asyncio.run(check())
