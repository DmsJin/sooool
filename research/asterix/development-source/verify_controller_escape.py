"""Recorded-answer diagnostic only: not a new policy rollout or causal survival proof."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from simulate_5x import make_env
from hop_controller_v2 import HopControllerV2, VERTICAL


def run(root):
    steps = [json.loads(l) for l in (root/'steps.jsonl').read_text().splitlines()]
    requests = [json.loads(l) for l in (root/'requests.jsonl').read_text().splitlines()]
    actions = json.loads((root/'actions.json').read_text())
    ready = defaultdict(list)
    for row in requests:
        if row.get('completion_observed_frame') is not None and row.get('action_valid'):
            ready[row['completion_observed_frame']].append(row)
    summaries = []
    for patched in [False, True]:
        env,obs,info,noops = make_env(2)
        controller = HopControllerV2()
        old = [r for r in actions if r['frame']<158]
        controller.action = steps[157]['action']
        controller.last = max((r['seq'] for r in old), default=-1)
        controller.vertical_finished = max((r['frame']+4 for r in old if r['action'] in VERTICAL and 'reason' not in r), default=-1)
        first_life_loss = None
        prior_lives = info.get('lives')
        trace = []
        for frame, step in enumerate(steps[:301]):
            action = controller.advance(frame,ready[frame]) if patched and frame>=158 else step['action']
            obs,reward,done,truncated,info = env.step(action)
            lives = info.get('lives')
            if lives < prior_lives and first_life_loss is None:
                first_life_loss = frame
            prior_lives = lives
            if 158<=frame<=164:
                trace.append({'frame':frame,'action':action})
        summaries.append({'mode':'v2_with_prerecorded_answers' if patched else 'recorded_original',
                          'through_frame':300,'first_life_loss_frame':first_life_loss,
                          'lives':info.get('lives'),'trace':trace,'model_calls':0})
        env.close()
    return {'diagnostic':summaries,'limitation':'After divergence, prerecorded answers came from old observations. This does not measure the new policy survival rate.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    print(json.dumps(run(a.root)))
