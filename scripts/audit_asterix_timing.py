"""Audit sampled delays and single-request delivery chronology; no model calls."""
import argparse
import json
import math
from pathlib import Path
import random
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('episode',type=Path);p.add_argument('--profile',type=Path);p.add_argument('--delay-seed-offset',type=int);p.add_argument('--report',type=Path);a=p.parse_args()
summary=json.loads((a.episode/'summary.json').read_text())
if summary.get('mode')=='realtime':p.error('Realtime uses actual delivery timestamps, not sampled profile draws.')
recipe=json.loads((ROOT/'recipes/asterix.json').read_text())
for parent in a.episode.resolve().parents:
 if (parent/'manifest.json').exists():
  recipe=json.loads((parent/'manifest.json').read_text())['recipe'];break
profile=json.loads((a.profile or ROOT/recipe['profile']).read_text())
offset=a.delay_seed_offset if a.delay_seed_offset is not None else recipe['args']['latency_seed_offset']
path=next((a.episode/n for n in ('issued.jsonl','requests.jsonl','decisions.jsonl') if (a.episode/n).exists()),None)
if path is None:p.error('No saved request records.')
rows=[json.loads(x) for x in path.read_text().splitlines()]
rng=random.Random(offset+summary['seed'])
for row in rows:
 seconds=rng.choice(profile['capture_to_complete_seconds'])
 assert row['sampled_capture_to_complete_s']==seconds,'Sample calendar changed'
 assert row['action_ready_frame']==row['obs_frame']+max(1,math.ceil(seconds*12)),'Frame conversion changed'
serial=all(cur['obs_frame']>=prev['action_ready_frame'] for prev,cur in zip(rows,rows[1:]))
if recipe['args'].get('virtual_capacity')==1:assert serial,'Overlapping requests in a serial recipe'
result={'game':'asterix','verified_draws':len(rows),'virtual_raw_fps':12,'sampling':'empirical IID','seed':offset+summary['seed'],'single_request_chronology':serial,'all_ready_frames_match':True,'model_calls':0}
if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
