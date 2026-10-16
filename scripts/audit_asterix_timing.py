"""Audit recorded CDF-equivalent draws and action-ready frames, no model calls."""
import argparse
import json
import math
from pathlib import Path
import random
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('episode',type=Path);p.add_argument('--profile',type=Path,default=ROOT/'profiles/asterix/latency_5x_empirical.json');p.add_argument('--report',type=Path);a=p.parse_args()
summary=json.loads((a.episode/'summary.json').read_text());profile=json.loads(a.profile.read_text())
requests=a.episode/'issued.jsonl';rows=[json.loads(x)for x in requests.read_text().splitlines()]
rng=random.Random(42+summary['seed'])
for row in rows:
 seconds=rng.choice(profile['capture_to_complete_seconds'])
 assert row['sampled_capture_to_complete_s']==seconds,'Sample calendar changed'
 assert row['action_ready_frame']==row['obs_frame']+max(1,math.ceil(seconds*12)),'Frame conversion changed'
result={'game':'asterix','verified_draws':len(rows),'virtual_raw_fps':12,'sampling':'empirical IID; inverse discrete CDF equivalent','seed':42+summary['seed'],'all_ready_frames_match':True,'model_calls':0}
if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
