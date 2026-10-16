"""Re-execute saved model actions in original environments; zero model/API calls."""
import argparse
import asyncio
import base64
import hashlib
import heapq
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.cli import serve

def rows(p):return [json.loads(x)for x in Path(p).read_text().splitlines()]

async def rhythm(root):
    sys.path.insert(0,str(ROOT/'environments/rhythm'))
    from experiments.rhythm.model_env import ModelVisualEnv
    captures=rows(root/'captures.jsonl');decisions=rows(root/'decisions.jsonl')
    old=json.loads((root/'frozen.json').read_text());events=[]
    for i,c in enumerate(captures):heapq.heappush(events,(c['virtual_s'],1,i))
    for i,d in enumerate(decisions):heapq.heappush(events,(d['delivery_virtual_s'],0,i))
    checked=0;pixel_mismatches=0
    with serve(ROOT/'environments/rhythm/dist')as url:
        async with ModelVisualEnv(url,virtual=True,chart_path=ROOT/'policies/rhythm/v19/chart.json',clock_offset_ms=old['clock_offset_ms'])as env:
            await env.start()
            while events:
                t,kind,i=heapq.heappop(events);await env.advance(t)
                if kind==0:
                    d=decisions[i]
                    if 'plan'in d:await env.apply(d['plan'])
                else:
                    c=captures[i];image=await env.capture()
                    if hashlib.sha256(image['png']).hexdigest()!=c['image_sha256']:
                        pixel_mismatches+=1
                    checked+=1
            await env.advance(old['duration_s']);actual=await env.trusted_evaluator()
    expected=json.loads((root/'summary.json').read_text())['evaluator']
    assert actual==expected,(actual,expected)
    return {'game':'rhythm','model_calls':0,'mode':'saved_action_replay','captures_compared':checked,'pixel_hash_mismatches':pixel_mismatches,'pixel_note':'Cross-browser/rendering hashes are diagnostic; exact evaluator state is required.','evaluator':actual,
        'strict_full_combo':actual['counts']['miss']==0 and actual['max_combo']==52}

def touhou(root):
    sys.path.insert(0,str(ROOT/'environments/touhou'))
    from research.environment import BrowserEnv
    summary=json.loads((root/'summary.json').read_text());actions=[x for x in rows(root/'actions.jsonl')if x.get('status','applied')=='applied']
    with serve(ROOT/'environments/touhou/dist')as url:
        with BrowserEnv(url)as env:
            env.reset(seed=summary['seed'],mode='sim',speed=1)
            visual=0
            for a in actions:
                target=a['visual_frame']
                if target>visual:env.advance(target-visual)
                env.apply(a['plan']);visual=target
            final=summary['visual_frames']
            if final>visual:env.advance(final-visual)
            actual=env.diagnostics()['state']
    expected=json.loads((root/'final_state.json').read_text());expected.pop('clock',None)
    assert actual==expected,'Final Touhou engine state differs from saved trajectory'
    return {'game':'touhou','model_calls':0,'mode':'saved_action_replay_of_original_'+summary['mode'],
        'verified_actions':len(actions),'status':actual['status'],'game_s':summary['game_s'],'hits':summary['hits']}

def asterix(root):
    sys.path.insert(0,str(ROOT/'environments/asterix'));from simulate_5x import verify_replay
    # Historical simulated runs call this issued.jsonl; the original helper expects requests.jsonl.
    # Use a temporary view rather than mutating historical evidence.
    import tempfile,shutil
    with tempfile.TemporaryDirectory(prefix='asterix-replay-')as d:
        view=Path(d)
        for name in ('summary.json','steps.jsonl'):shutil.copy2(root/name,view/name)
        issued=next((root/name for name in ('requests.jsonl','issued.jsonl','decisions.jsonl') if (root/name).exists()),None)
        if issued is None:raise ValueError('No saved request records')
        shutil.copy2(issued,view/'requests.jsonl')
        return {'game':'asterix','mode':'saved_action_replay',**verify_replay(view)}

def main():
    p=argparse.ArgumentParser();p.add_argument('game',choices=['rhythm','touhou','asterix']);p.add_argument('episode',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    r=asyncio.run(rhythm(a.episode))if a.game=='rhythm'else globals()[a.game](a.episode)
    if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
if __name__=='__main__':main()
