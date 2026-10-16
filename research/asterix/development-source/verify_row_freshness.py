"""Fixed recorded-answer branches: controller diagnostics, not new policy scores."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from simulate_5x import make_env
from hop_controller_v2 import HopControllerV2
from hop_controller_v3 import HopControllerV3


def run(root):
    p=root/'seed-6'
    steps=[json.loads(l) for l in (p/'steps.jsonl').read_text().splitlines()]
    issued=[json.loads(l) for l in (p/'issued.jsonl').read_text().splitlines()]
    ready=defaultdict(list)
    for r in issued:
        f=p/f"call-{r['seq']:05d}"/'result.json'
        if f.exists():
            ready[r['action_ready_frame']].append({'seq':r['seq'],'obs_frame':r['obs_frame'],'chosen':json.loads(f.read_text())['chosen']})
    results=[]
    for start,stop in [(184,344),(447,609)]:
        assert len(steps)>stop
        for patched in [False,True]:
            env,obs,info,noops=make_env(6)
            old=HopControllerV2();new=None;losses=[];lives=3
            try:
                for frame in range(stop+1):
                    if patched and frame==start:
                        new=HopControllerV3()
                        new.action,new.last,new.vertical_finished=old.action,old.last,old.vertical_finished
                    controller=new if new else old
                    action=controller.advance(frame,ready[frame])
                    if new is None: assert action==steps[frame]['action'],frame
                    obs,reward,done,truncated,info=env.step(action)
                    if info.get('lives')<lives:losses.append(frame)
                    lives=info.get('lives')
                results.append({'branch_start':start,'through_frame':stop,'controller':'v3' if patched else 'v2',
                                'lives':lives,'life_loss_frames':losses,'model_calls':0})
            finally:env.close()
    return {'branches':results,'limitation':'After branch, old answers refer to old observations. These are execution diagnostics; new closed-loop rollouts remain necessary.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();print(json.dumps(run(a.root)))
