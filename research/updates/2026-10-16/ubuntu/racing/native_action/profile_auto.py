"""Strictly serial real API profiling, native actuator output, raw images only."""
import sys,pathlib,json,random,statistics,getpass,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from run import API,Budget,MINIMAL_SYSTEM,write,append
import policy
ROOT=pathlib.Path(__file__).resolve().parents[1]
out=ROOT/'results/native-profile-auto-v2';out.mkdir(parents=True,exist_ok=False)
samples=pathlib.Path('/home/ubuntu/wzh/racing-autoresearch-20261015/results/round6/minimal-metric-5x-s101')
conditions=[{'images':n,'chunk':c,'anchor':'issue' if c==3 else 'arrival'} for n in [2,3] for c in [1,3]]
trials=[(j,c,k) for j,c in enumerate(conditions) for k in range(6)];random.Random(1701).shuffle(trials)
write(out/'manifest.json',{'paid_api_concurrency':1,'background_subscription_jobs':False,'conditions':conditions,'samples':'development seed101 only','raw_camera_only':True,'image_detail':'auto','executor':'blind timed actuator delivery','total_calls':24})
api=API(getpass.getpass('API credential for strict serial native-action profiling (memory only): '),Budget(ROOT/'research-results/budget.json'),'native_profile_auto',1.8,instructions=MINIMAL_SYSTEM,image_detail='auto');measurements=[]
try:
 for i,(j,c,k) in enumerate(trials):
  index=[0,50,100,170,240,310][k];ids=[max(0,index-3*(c['images']-1-x)) for x in range(c['images'])];states=[];images=[]
  for ident in ids:
   folder=samples/f'decision_{ident:05d}';d=json.loads((folder/'input.json').read_text());text=d['prompt'].split('Visible observations: ',1)[1];state=json.JSONDecoder().raw_decode(text)[0][-1];states.append(policy.visible(state));images.append((folder/'image_0.png').read_bytes())
  task=policy.prompt(states,'predict',c['chunk'],c['anchor'],{'unknown':'serial profiling in progress'})
  validate=lambda text:policy.parse(text,c['chunk'],c['anchor'])
  answer,meta=api.act(task,images,out/f'call_{i:03d}',on_ready=lambda a,m:None,validator=validate)
  try:commands=validate(answer);valid=True
  except (ValueError,TypeError):commands=None;valid=False
  row={'index':i,'condition':j,**c,'valid':valid,'commands':commands,**meta};measurements.append(row);append(out/'measurements.jsonl',row);print(json.dumps({'index':i,'condition':j,'valid':valid,'json_ready':meta['json_ready_seconds'],'full':meta['wall_seconds']}),flush=True)
finally:api.close()
for j,c in enumerate(conditions):
 rows=[r for r in measurements if r['condition']==j];values=[r['published_seconds'] or r['wall_seconds'] for r in rows];v=sorted(values)
 summary={'condition':c,'n':len(rows),'valid_outputs':sum(r['valid'] for r in rows),'concurrency':1,'min':min(v),'p50':statistics.median(v),'p95':v[-1],'mean':statistics.mean(v),'delays':values,'latency_endpoint':'complete legal JSON publication; EOF fallback for invalid output','model':'gpt-6.1-sol','service_tier':'ultrafast','effort':'low','image_detail':'auto'}
 write(out/f'condition_{j}.json',summary);print('CONDITION '+json.dumps(summary),flush=True)
