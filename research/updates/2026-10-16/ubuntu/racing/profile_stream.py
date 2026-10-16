"""Strictly serial paid API profiling of actual frozen winning-policy inputs."""
import argparse,getpass,hashlib,json,pathlib,random,statistics,time
from run import WORK_ROOT,API,Budget,MINIMAL_SYSTEM,MODEL,ROOT,parse,write,append


def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--calls',type=int,default=16);p.add_argument('--budget',type=pathlib.Path,default=WORK_ROOT/'research-results/budget.json');a=p.parse_args()
 a.out.mkdir(parents=True,exist_ok=False);rng=random.Random(20261015);samples=[]
 for seed in [101,111]:
  episode=WORK_ROOT/f'results/round6/minimal-metric-5x-s{seed}'
  files=sorted(episode.glob('decision_*/input.json'));n=a.calls//2
  for i in range(n):
   lo=int((i+.15)*len(files)/n);hi=int((i+.85)*len(files)/n)
   samples.append(files[rng.randrange(lo,max(lo+1,hi))])
 rng.shuffle(samples)
 write(a.out/'manifest.json',{'source_inputs':[str(f) for f in samples],'model':MODEL,'effort':'low','service_tier':'ultrafast','system':'minimal','paid_api_concurrency':1,'subscription_jobs_parallel':True,'note':'Frozen actual game prompts and pixels; direct API omits Codex runtime tool wrappers. Background subscription experiments remain active; compare to initial idle serial profile separately.'})
 client=API(getpass.getpass('API credential for serial frozen-policy profiling (memory only): '),Budget(a.budget),'profile',2,instructions=MINIMAL_SYSTEM)
 rows=[];started=time.monotonic()
 try:
  for i,f in enumerate(samples):
   inp=json.loads(f.read_text());images=[q.read_bytes() for q in sorted(f.parent.glob('image_*.png'))]
   if [hashlib.sha256(b).hexdigest() for b in images]!=inp['image_sha256']:raise RuntimeError('frozen image hash mismatch')
   answer,meta=client.act(inp['prompt'],images,a.out/f'call_{i:03d}',on_ready=lambda commands,meta: None,validator=lambda text: parse(text,1))
   commands=parse(answer,1);row={'index':i,'commands':commands,**meta};rows.append(row);append(a.out/'measurements.jsonl',row)
   print('FROZEN_PROFILE '+json.dumps({'index':i,'seconds':meta['wall_seconds'],'input_tokens':meta['usage']['input_tokens'],'output_tokens':meta['usage']['output_tokens']}),flush=True)
 finally:client.close()
 values=sorted(r['wall_seconds'] for r in rows)
 summary={'n':len(rows),'concurrency':1,'all_outputs_valid':True,'min':min(values),'p50':statistics.median(values),'p95':values[min(len(values)-1,__import__('math').ceil(.95*len(values))-1)],'mean':statistics.mean(values),'delays':values,'model':MODEL,'effort':'low','service_tier':'ultrafast','system':'minimal','wall_seconds':time.monotonic()-started,'subscription_jobs_parallel':True}
 write(a.out/'profile.json',summary);print('FROZEN_PROFILE_DONE '+json.dumps(summary),flush=True)

if __name__=='__main__':main()
