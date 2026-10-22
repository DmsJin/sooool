"""Serial API latency profiling with exact completed-game menu inputs.
Dry-run is the default. API keys are read by getpass only for --run-paid.
"""
import argparse,base64,getpass,hashlib,json,random,statistics
from pathlib import Path
from paid import API,Budget

def prepare(source,calls):
 summary=json.loads((source/'summary.json').read_text())
 if not summary['finished'] or summary.get('failure'):raise ValueError('Use a completed episode as the profiling source')
 groups={k:[] for k in ['wait','move','serve_bundle','act']}
 for line in (source/'episode.jsonl').read_text().splitlines():
  event=json.loads(line)
  if event['ev']!='model_issued':continue
  seq=event['seq'];directory=source/f'decision_{seq:05d}'
  if not (directory/'result.json').exists():continue
  try:
   result=json.loads((directory/'result.json').read_text());choice=json.loads(result['answer'])['choice']
   options=event['options']
   if type(choice)!=int or not 0<=choice<len(options):continue
   kind=options[choice]['kind']
  except (ValueError,KeyError,IndexError,TypeError):continue
  text=json.loads((directory/'input.json').read_text())['params']['input'][0]['text']
  image=(source/'observations'/f'{seq:05d}.png').read_bytes();image_hash=hashlib.sha256(image).hexdigest()
  if image_hash!=event['image_sha256']:raise ValueError('Source observation hash mismatch')
  groups[kind].append({'seq':seq,'kind':kind,'prompt':text,'image_b64':base64.b64encode(image).decode(),'options':options})
 rng=random.Random(816);selected=[]
 for group in groups.values():rng.shuffle(group)
 # Balance distinct source observations across the available action categories.
 while len(selected)<calls and any(groups.values()):
  for kind in ['serve_bundle','act','move','wait']:
   if groups[kind] and len(selected)<calls:selected.append(groups[kind].pop())
 if len(selected)<min(calls,6):raise ValueError('Too few distinct source observations')
 rng.shuffle(selected)
 return selected,summary

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--calls',type=int,default=24);p.add_argument('--run-paid',action='store_true');a=p.parse_args()
 if not 6<=a.calls<=48:raise ValueError('Choose between six and 48 serial calls')
 samples,source_summary=prepare(a.source,a.calls)
 plan={'source':str(a.source),'source_digest':source_summary['digest'],'variant':source_summary['variant'],'model':'gpt-6.1-sol','service_tier':'ultrafast','effort':'low','concurrency':1,'game_prompt_and_observation_preserved':True,'samples':[{k:s[k] for k in ['seq','kind']} for s in samples]}
 a.output.mkdir(parents=True,exist_ok=False);(a.output/'plan.json').write_text(json.dumps(plan,indent=2))
 if not a.run_paid:print(json.dumps({'paid_calls':0,'planned_calls':len(samples),'plan':str(a.output/'plan.json')}));return
 key=getpass.getpass('API key (memory only): ');api=API(key,Budget(a.ledger),'profiling',5);key=None;rows=[]
 try:
  for sample in samples:
   items=[{'role':'user','content':[{'type':'input_text','text':sample['prompt']},{'type':'input_image','detail':'high','image_url':'data:image/png;base64,'+sample['image_b64']}]}]
   count=api.count(items);row=api.call(items,effort='low',count=count)
   try:
    answer=json.loads(row['answer']);choice=answer['choice'];valid=type(choice)==int and set(answer)=={'choice'} and 0<=choice<len(sample['options'])
   except (ValueError,KeyError,TypeError):valid=False
   row.update(seq=sample['seq'],source_kind=sample['kind'],returned_kind=sample['options'][choice]['kind'] if valid else 'invalid',action_contract_valid=valid,input_token_count=count,concurrency=1);rows.append(row)
   with (a.output/'requests.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
   print(json.dumps({k:row[k] for k in ['seq','status','request_s','cost_usd','action_contract_valid','error']}),flush=True)
   if row['error'] or row['status']!='completed':break
 finally:api.http.close()
 delays=sorted(r['request_s'] for r in rows if r['status']=='completed' and not r['error'])
 # Completed invalid actions remain in the measured distribution; never discard
 # their latency to make the profile look faster.
 report={'model':'gpt-6.1-sol','service_tier':'ultrafast','effort':'low','image_detail':'high','concurrency':1,'attempts':len(rows),'completed':len(delays),'valid':sum(r['action_contract_valid'] for r in rows),'cost_usd':sum(r['cost_usd'] for r in rows),'delays_s':delays,'min_s':min(delays) if delays else None,'p50_s':statistics.median(delays) if delays else None,'p95_s':delays[max(0,(95*len(delays)+99)//100-1)] if delays else None,'source_digest':source_summary['digest'],'variant':source_summary['variant'],'source_kind_counts':{k:sum(r['source_kind']==k for r in rows) for k in ['wait','move','serve_bundle','act']},'returned_kind_counts':{k:sum(r['returned_kind']==k for r in rows) for k in ['wait','move','serve_bundle','act','invalid']},'scope':'serial exact-menu-input API profile; no live gameplay claim'}
 (a.output/'profile.json').write_text(json.dumps(report,indent=2));print('SUMMARY',json.dumps(report),flush=True)
if __name__=='__main__':main()
