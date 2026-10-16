"""Serial, real-image API profiling. Never starts parallel API calls."""
import argparse
import getpass
import json
from pathlib import Path
import statistics
from paid import API,Budget
from policy import inputs,parse

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--samples',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--ledger',type=Path,required=True)
    ap.add_argument('--calls',type=int,default=24)
    a=ap.parse_args()
    spec=json.loads((a.samples/'spec.json').read_text())
    files=sorted(a.samples.glob('sample_*.json'))
    if len(files)<6:raise RuntimeError('Need representative native observations')
    a.output.mkdir(parents=True,exist_ok=False)
    key=getpass.getpass('API key (memory only): ')
    api=API(key,Budget(a.ledger),'profiling',5)
    key=None
    rows=[]
    for i in range(a.calls):
        sample=files[i%len(files)]
        view=json.loads(sample.read_text())
        items=inputs(view,spec)
        count=api.count(items)
        r=api.call(items,effort='low',count=count)
        try:parse(r['answer']);r['action_valid']=True
        except (ValueError,TypeError):r['action_valid']=False
        r.update(index=i,sample=sample.name,input_token_count=count,concurrency=1)
        rows.append(r)
        with (a.output/'requests.jsonl').open('a') as f:f.write(json.dumps(r)+'\n')
        print(json.dumps({k:r[k] for k in ('index','status','request_s','ttft_s','cost_usd','action_valid','error')}),flush=True)
        if r['error'] or r['status']!='completed':break
    valid=[r['request_s'] for r in rows if r['status']=='completed' and r['action_valid']]
    valid.sort()
    summary={'model':'gpt-6.1-sol','service_tier':'ultrafast','effort':'low','image_detail':'high','concurrency':1,
             'attempts':len(rows),'valid':len(valid),'cost_usd':sum(r['cost_usd'] for r in rows),
             'delays_s':valid,'min_s':min(valid) if valid else None,'p50_s':statistics.median(valid) if valid else None,
             'p95_s':valid[max(0,(95*len(valid)+99)//100-1)] if valid else None,
             'scope':'serial fixed-observation screening profile; no live gameplay result'}
    (a.output/'profile.json').write_text(json.dumps(summary,indent=2))
    print('SUMMARY '+json.dumps(summary),flush=True)
    api.http.close()

if __name__=='__main__':main()
