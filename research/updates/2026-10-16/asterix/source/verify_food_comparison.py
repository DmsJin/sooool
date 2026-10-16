"""Independent zero-model replay of completed full-game comparison episodes."""
import argparse
from collections import deque, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
from hop_controller_v3 import HopControllerV3
from simulate_5x import make_env, png, select_images


def audit(directory, profile):
    summary=json.loads((directory/'summary.json').read_text())
    assert summary['error'] is None
    steps=[json.loads(x) for x in (directory/'steps.jsonl').read_text().splitlines()]
    decisions=[json.loads(x) for x in (directory/'decisions.jsonl').read_text().splitlines()]
    config=json.loads((directory.parent/'config.json').read_text())
    assert config['profile_sha256']==hashlib.sha256(profile.read_bytes()).hexdigest()
    assert len(steps)==summary['frames'] and len(decisions)==summary['calls']
    assert summary['replayed_calls']==0 and summary['paid_api_calls']==0
    assert [r['seq'] for r in decisions]==list(range(len(decisions)))
    issued={r['obs_frame']:r for r in decisions}
    assert len(issued)==len(decisions)
    delays=json.loads(profile.read_text())['capture_to_complete_seconds']
    rng=random.Random(config['latency_seed_offset']+summary['seed'])
    ready=defaultdict(list)
    for r in decisions:
        assert type(r['chosen']) is int and 0<=r['chosen']<=8
        assert r['obs_frame']%4==0
        assert r['sampled_capture_to_complete_s']==rng.choice(delays)*config['latency_scale']
        assert r['action_ready_frame']==r['obs_frame']+math.ceil(r['sampled_capture_to_complete_s']*12)
        assert r['meta']['wrapper_profile']=='minimal'
        ready[r['action_ready_frame']].append(r)
    env,obs,info,noops=make_env(summary['seed'])
    assert noops==summary['reset_noops']
    controller=HopControllerV3();window=deque(maxlen=9);score=0.;checked=0
    try:
        for f,step in enumerate(steps):
            assert step['frame']==f
            action=controller.advance(f,ready[f])
            assert action==step['action'],('executor',f)
            assert sum(r['obs_frame']<=f<r['action_ready_frame'] for r in decisions)<=8
            if f%4==0:window.append((f,png(obs)))
            if f in issued:
                r=issued[f];images=select_images(window)
                assert r['held_action']==action
                assert r['image_frames']==[t for t,_ in images]
                assert r['image_sha256']==[hashlib.sha256(im).hexdigest() for _,im in images],('images',f)
                assert r['score_at_issue']==score
                checked+=1
            obs,reward,done,truncated,info=env.step(action);score+=reward
            assert reward==step['reward'] and score==step['score'] and info['lives']==step['lives'],('game',f)
            if done or truncated:assert f==len(steps)-1 and summary['status']=='natural_end'
    finally:env.close()
    assert score==summary['score'] and info['lives']==summary['lives']
    assert checked==len(decisions)
    assert controller.applied==json.loads((directory/'actions.json').read_text())
    assert controller.ignored==json.loads((directory/'ignored_commands.json').read_text())
    return {'seed':summary['seed'],'frames':len(steps),'verified_request_images':checked,
            'score':score,'lives':info['lives'],'verification_model_calls':0,
            'checkpoints':[{'game_seconds':n/60,'score':steps[n-1]['score'],'lives':steps[n-1]['lives']}
                           for n in range(300,len(steps)+1,300)]}


def main(root,profile):
    protocol=json.loads((root/'protocol.json').read_text());results=[];pending=[]
    for job in protocol['episode_schedule']:
        directory=root/job['policy']/f"repeat-{job['repeat']}"/f"seed-{job['seed']}"
        if not (directory/'summary.json').exists():
            pending.append(job);continue
        summary=json.loads((directory/'summary.json').read_text())
        if summary.get('error'):
            pending.append({**job,'error':summary['error']});continue
        result={**job,**audit(directory,profile)}
        (directory/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n')
        results.append(result)
    report={'verified':results,'pending_or_error':pending,'complete':not pending,
            'verification_model_calls':0}
    (root/'independent_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path)
    p.add_argument('--profile',type=Path,required=True)
    args=p.parse_args();main(args.root,args.profile)
