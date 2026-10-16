"""Paired, randomized subscription context benchmark. No paid API calls.
Preserves each saved prompt and native image byte-for-byte. Measures response
latency and action-contract quality; agreement is not a win-rate estimate.
"""
import argparse,base64,hashlib,json,random,statistics,time
from pathlib import Path
from subscription import SubscriptionClient

def percentile(xs,q):
 xs=sorted(xs);return xs[min(len(xs)-1,round((len(xs)-1)*q))]

def run(a):
 a.output.mkdir(parents=True)
 rng=random.Random(814)
 groups={k:[] for k in ('serve','return','move','wait')}
 for line in (a.source/'episode.jsonl').read_text().splitlines():
  event=json.loads(line)
  if event.get('ev',event.get('kind',event.get('type',event.get('event'))))!='model_issued':continue
  seq=event['seq'];options=event['options'];kinds={o['kind'] for o in options}
  group='serve' if 'serve_bundle' in kinds else 'return' if 'act' in kinds else 'move' if 'move' in kinds else 'wait'
  groups[group].append((seq,options))
 selected=[]
 for group,n in [('serve',6),('return',8),('move',6),('wait',4)]:
  values=groups[group];rng.shuffle(values)
  selected.extend({'seq':seq,'options':opts,'stratum':group} for seq,opts in values[:n])
 if len(selected)<24:
  used={x['seq'] for x in selected};others=[(seq,opts,g) for g,vs in groups.items() for seq,opts in vs if seq not in used];rng.shuffle(others)
  selected.extend({'seq':seq,'options':opts,'stratum':g} for seq,opts,g in others[:24-len(selected)])
 rng.shuffle(selected)
 if not selected:raise ValueError('No model_issued samples found')
 for sample in selected:
  seq=sample['seq'];p=a.source/f'decision_{seq:05d}'/'input.json';sample['prompt']=json.loads(p.read_text())['params']['input'][0]['text']
  sample['image']=base64.b64encode((a.source/'observations'/f'{seq:05d}.png').read_bytes()).decode()
 plan={'random_seed':814,'pairs':len(selected),'baseline':'current compact coding replacement with remaining Codex context','treatment':'requested compact prompt plus disabled unrelated blocks/tools and isolated config','effort':'low','paid_api_calls':0,'quality_scope':'JSON contract and paired action agreement; not ground-truth accuracy or closed-loop win rate','samples':[{'seq':s['seq'],'stratum':s['stratum'],'prompt_sha256':hashlib.sha256(s['prompt'].encode()).hexdigest(),'image_sha256':hashlib.sha256(base64.b64decode(s['image'])).hexdigest()} for s in selected]}
 (a.output/'plan.json').write_text(json.dumps(plan,indent=2))
 clients={};rows=[];started=time.monotonic()
 try:
  for cond in ('A','B'):
   clients[cond]=SubscriptionClient(Path('/home/ubuntu/lzj/coding-agent-suite'),a.output/cond,quota_stop_percent=99,compact_instructions=True,lean_context=cond=='B')
  # One warm-up per condition, excluded from paired estimates, still logged.
  jobs=[(True,-1,selected[0],['A','B'])]
  for i,sample in enumerate(selected):
   order=['A','B'];rng.shuffle(order);jobs.append((False,i,sample,order))
  for warmup,i,sample,order in jobs:
   for cond in order:
    directory=a.output/('warmup' if warmup else f'pair_{i:03d}')/cond
    before=time.monotonic()
    answer,meta=clients[cond].act(sample['prompt'],[base64.b64decode(sample['image'])],directory)
    total=time.monotonic()-before
    try:
     parsed=json.loads(answer);choice=parsed['choice'];valid=type(choice)==int and 0<=choice<len(sample['options']) and set(parsed)=={'choice'}
    except (ValueError,KeyError,TypeError):choice=None;valid=False
    usage=(meta.get('token_usage') or {}).get('last',{})
    events=[json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines()]
    errors='\n'.join(json.dumps(e.get('params',{})) for e in events if e.get('method')=='error')
    row={'pair':i,'warmup':warmup,'condition':cond,'seq':sample['seq'],'stratum':sample['stratum'],'answer':answer,'choice':choice,'valid':valid,'action_kind':sample['options'][choice]['kind'] if valid else None,'full_call_wall_s':total,**meta,'usage':usage,'retry_429_events':errors.count('429'),'retry_403_events':errors.count('403')}
    (directory/'result.json').write_text(json.dumps(row,indent=2));rows.append(row)
    with (a.output/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    print(json.dumps({k:row[k] for k in ['pair','condition','seq','valid','wall_seconds','full_call_wall_s','retry_429_events']}),flush=True)
  actual=[r for r in rows if not r['warmup']]
  summary={'pairs':len(selected),'wall_s':time.monotonic()-started,'paid_api_calls':0,'quality_scope':plan['quality_scope']}
  for cond in ('A','B'):
   rs=[r for r in actual if r['condition']==cond];times=[r['wall_seconds'] for r in rs]
   summary[cond]={'n':len(rs),'mean_s':statistics.mean(times),'p50_s':statistics.median(times),'p95_s':percentile(times,.95),'valid':sum(r['valid'] for r in rs),'retry_429_events':sum(r['retry_429_events'] for r in rs),'mean_full_call_s':statistics.mean(r['full_call_wall_s'] for r in rs),'mean_tokens':{key:statistics.mean(r['usage'].get(key,0) for r in rs) for key in ['inputTokens','cachedInputTokens','outputTokens','reasoningOutputTokens']}}
  pairs=[{r['condition']:r for r in actual if r['pair']==i} for i in range(len(selected))]
  summary['paired_choice_agreement']=sum(p['A']['choice']==p['B']['choice'] for p in pairs)
  summary['mean_latency_reduction_percent']=100*(1-summary['B']['mean_s']/summary['A']['mean_s'])
  boot=random.Random(815);deltas=[]
  for _ in range(5000):
   draw=boot.choices(pairs,k=len(pairs));deltas.append(statistics.mean(p['A']['wall_seconds']-p['B']['wall_seconds'] for p in draw))
  summary['paired_mean_s_saved_bootstrap_95ci']=[percentile(deltas,.025),percentile(deltas,.975)]
  (a.output/'summary.json').write_text(json.dumps(summary,indent=2));print('SUMMARY',json.dumps(summary),flush=True)
 finally:
  for client in clients.values():client.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
