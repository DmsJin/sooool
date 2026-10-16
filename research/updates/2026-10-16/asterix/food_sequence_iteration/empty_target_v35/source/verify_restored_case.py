"""Independent artifact replay of restored native-policy case windows; no model."""
import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
from hop_controller_v3 import HopControllerV3
from simulate_5x import make_env,png,select_images


def verify(episode,root):
    prefix=[json.loads(x) for x in (episode/'steps.jsonl').read_text().splitlines()]
    original_actions=json.loads((episode/'actions.json').read_text())
    results=[]
    for directory in sorted(root.glob('food_route_*-repeat*')):
        summary=json.loads((directory/'summary.json').read_text());start=summary['start_frame']
        steps=[json.loads(x) for x in (directory/'steps.jsonl').read_text().splitlines()]
        decisions=[json.loads(x) for x in (directory/'decisions.jsonl').read_text().splitlines()]
        at_frame={r['obs_frame']:r for r in decisions};ready={}
        assert len(at_frame)==len(decisions)
        for row in decisions:
            assert row['action_ready_frame']==row['obs_frame']+math.ceil(row['sampled_capture_to_complete_s']*12)
            ready.setdefault(row['action_ready_frame'],[]).append(row)
        env,obs,info,_=make_env(summary.get('seed',5));window=deque(maxlen=9);score=0.
        controller=HopControllerV3();controller.applied=[dict(a) for a in original_actions if a['frame']<start]
        controller.action=prefix[start-1]['action']
        if controller.action in (1,4,5,6,7,8):
            controller.vertical_finished=next(a['frame'] for a in reversed(controller.applied) if a['action'] in (1,4,5,6,7,8))+4
        checked=0
        try:
            for f in range(start):
                if f%4==0:window.append((f,png(obs)))
                obs,reward,_,_,info=env.step(prefix[f]['action']);score+=reward
                assert reward==prefix[f]['reward'] and info['lives']==prefix[f]['lives']
            assert score==summary['initial_score']
            for step in steps:
                f=step['frame'];rows=ready.get(f,[])
                newest=max(rows,key=lambda r:r['seq']) if rows else None
                valid=[newest] if newest is not None and newest['seq']>controller.last else []
                action=controller.advance(f,valid)
                assert action==step['action'],('controller',f)
                if f%4==0:window.append((f,png(obs)))
                if f in at_frame:
                    row=at_frame[f];images=select_images(window)
                    assert row['image_frames']==[t for t,_ in images]
                    assert row['image_sha256']==[hashlib.sha256(im).hexdigest() for _,im in images]
                    assert sum(r['obs_frame']<=f<r['action_ready_frame'] for r in decisions)<=8
                    checked+=1
                obs,reward,_,_,info=env.step(action);score+=reward
                assert reward==step['reward'] and score==step['score'] and info['lives']==step['lives'],('game',f)
        finally:env.close()
        assert score==summary['score'] and checked==len(decisions)
        assert controller.applied==json.loads((directory/'actions.json').read_text())
        assert controller.ignored==json.loads((directory/'ignored.json').read_text())
        results.append({'label':summary['label'],'replayed_prefix_frames':start,'verified_new_frames':len(steps),
            'verified_request_images':checked,'reward_events':[{'frame':s['frame'],'reward':s['reward']} for s in steps if s['reward']],
            'score':score,'lives':info['lives'],'verification_model_calls':0})
    (root/'verification.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('episode',type=Path);p.add_argument('root',type=Path);a=p.parse_args();verify(a.episode,a.root)
