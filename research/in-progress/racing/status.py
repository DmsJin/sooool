"""Compact, read-only experiment snapshot; no model calls and no credentials."""
import json,pathlib,time,sys
root=pathlib.Path(__file__).resolve().parents[2]
report={'captured_at_unix':time.time(),'rounds':{}}
for folder in sorted((root/'results').glob('round*')):
 if not folder.is_dir() or (len(sys.argv)>1 and folder.name!=sys.argv[1]):continue
 episodes=[]
 for d in sorted(folder.iterdir()):
  if not d.is_dir():continue
  summary=json.loads((d/'summary.json').read_text()) if (d/'summary.json').exists() else {}
  issued=(d/'issued.jsonl').read_text().splitlines() if (d/'issued.jsonl').exists() else []
  last=json.loads(issued[-1]) if issued else {}
  legal={}
  inputs=sorted(d.glob('decision_*/input.json'))
  if inputs:
   prompt=json.loads(inputs[-1].read_text()).get('prompt','')
   if 'Visible observations: ' in prompt:
    visible,_=json.JSONDecoder().raw_decode(prompt.split('Visible observations: ',1)[1]);legal=visible[-1]
  episodes.append({'heat':legal.get('heat'),'heat_score':legal.get('race',{}).get('heats_won'),'id':d.name,'status':summary.get('status','running'),'won':summary.get('won'),'checkpoints':summary.get('scores',{}).get('A',{}).get('checkpoints'),'replay_matches':summary.get('replay_matches'),'issued':len(issued),'game_seconds_at_latest_observation':round(last.get('seen_step',0)*.01,2),'error':summary.get('error')})
 groups=json.loads((folder/'groups.json').read_text()) if (folder/'groups.json').exists() else None
 report['rounds'][folder.name]={'episodes':episodes,'groups':groups}
p=root/'research-results/budget.json'
if p.exists():report['paid_budget']=json.loads(p.read_text())
print(json.dumps(report,indent=2))
