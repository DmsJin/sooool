"""Zero-inference audit of V3 realtime game, executor, clock, cost and latency."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import statistics

from hop_controller_v3 import HopControllerV3
from profile_policy_latency import usage_cost, stats
from simulate_5x import verify_replay


def analyze(root):
    summary=json.loads((root/'summary.json').read_text())
    results=[]
    rewards=[]
    all_requests=[]
    for episode in summary['episodes']:
        directory=root/f"slow5-seed{episode['seed']}"
        steps=[json.loads(line) for line in (directory/'steps.jsonl').read_text().splitlines()]
        requests=[json.loads(line) for line in (directory/'requests.jsonl').read_text().splitlines()]
        all_requests.extend(requests)
        ready=defaultdict(list)
        for row in requests:
            if row.get('completion_observed_frame') is not None and row['status']=='completed' and row.get('action_valid'):
                ready[row['completion_observed_frame']].append(row)
        controller=HopControllerV3()
        for row in steps:
            actual=controller.advance(row['frame'],ready[row['frame']])
            assert actual==row['action'], ('executor mismatch',row['frame'])
        controller.advance(len(steps),ready[len(steps)])
        assert controller.applied==json.loads((directory/'actions.json').read_text())
        assert controller.ignored==json.loads((directory/'ignored.json').read_text())
        replay=verify_replay(directory)
        prior=0
        max_frames=json.loads((root/'protocol.json').read_text())['max_frames_each']
        for frame in range(300,max_frames+1,300):
            if frame<=len(steps):
                score=steps[frame-1]['score']; lives=steps[frame-1]['lives']
            elif episode['status']=='natural_end':
                score=episode['score'];lives=episode['lives']
            else:
                score=lives=None
            rewards.append({'seed':episode['seed'],'game_seconds':frame/60,'score':score,
                            'reward_last_5s':score-prior if score is not None and prior is not None else None,
                            'lives':lives})
            prior=score
        capture=[row['completed_monotonic']-row['captured_monotonic'] for row in requests]
        applied=[row['capture_to_apply_s'] for row in requests if row['disposition']=='applied']
        results.append({**episode,'replay_verified':replay,
            'dispositions':dict(Counter(row['disposition'] for row in requests)),
            'capture_to_complete_mean_s':statistics.mean(capture) if capture else None,
            'capture_to_apply_mean_s':statistics.mean(applied) if applied else None,
            'usage_accounted_usd':sum(usage_cost(row['usage']) if row.get('usage') is not None else round(row['accounted_usd']*1e6) for row in requests)/1e6})
    ledger=[json.loads(line) for line in (root/'budget.jsonl').read_text().splitlines()]
    reserved={row['ticket']:row['micro_usd'] for row in ledger if row['event']=='reserve'}
    settled={row['ticket']:row['micro_usd'] for row in ledger if row['event']=='settle'}
    assert reserved.keys()==settled.keys(), 'Unsettled request reservation'
    assert all(settled[t]<=reserved[t] for t in reserved), 'Cost exceeded reservation'
    total=(sum(settled.values())+ledger[0]['prior_used_micro_usd'])/1e6
    assert total==summary['accounted_usd'] and total<=ledger[0]['limit_micro_usd']/1e6
    output={'status':summary['status'],'episodes':results,'latency':stats(all_requests),
        'total_accounted_usd':total,'pending_reservations':0,'requests':len(all_requests),
        'all_timing_valid':all(row['timing_valid'] for row in results),
        'verification_model_calls':0,'subscription_stop_authorized_percent':80,
        'caveat':'One rollout per seed; partial budget-stop episodes are not full 20s scores.'}
    (root/'analysis.json').write_text(json.dumps(output,indent=2)+'\n')
    with (root/'rewards_by_5s.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['seed','game_seconds','score','reward_last_5s','lives'])
        writer.writeheader();writer.writerows(rewards)
    print(json.dumps(output,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    analyze(parser.parse_args().root)
