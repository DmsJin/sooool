"""Serial real API profile of native forecast + actuator JSON in a conversation."""
import sys,pathlib,json,getpass,statistics,os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from run import API,Budget,MINIMAL_SYSTEM,write,append
import policy
root=pathlib.Path(__file__).resolve().parents[1];out=pathlib.Path(os.environ.get('RACING_SINGLE_PROFILE_OUT',str(root/'results/native-single-profile-v1')));out.mkdir(parents=True,exist_ok=False);source=root/'results/native-forecast-full-v1/gentle-chase-s131';old=json.loads((root/'results/native-profile-auto-v2/condition_3.json').read_text());write(out/'manifest.json',{'paid_api_concurrency':1,'background_subscription_jobs':False,'image_detail':'auto','history':'client-managed conversation including encrypted reasoning, store=false','schema':'single actuator row, max duration3','samples':'development seed101 recorded images, proposals not applied during offline profile','total_calls':6})
api=API(getpass.getpass('API credential for serial single-action profiling (memory only): '),Budget(root/'research-results/budget.json'),'native_single_profile',2,instructions=MINIMAL_SYSTEM,image_detail='auto',stateful=True);rows=[]
try:
 for i,index in enumerate([0,2,4,8,12,16]):
  folder=source/f'decision_{index:05d}';text=json.loads((folder/'input.json').read_text())['prompt'];states=json.loads(text.split('Visible observations:',1)[1]);images=[f.read_bytes() for f in sorted(folder.glob('image_*.png'))];marker='Known actuator schedule (your earlier outputs, not predictions; absolute game times):' if i==0 else 'Committed future actuator schedule:';committed=json.JSONDecoder().raw_decode(text.split(marker,1)[1])[0]
  task=policy.session_prompt(states,'gentle',1,'arrival',{k:old[k] for k in ['p50','p95','mean']},camera='chase',committed=committed,first=i==0,max_duration=3);head,obs=task.split('\nVisible observations:',1);task=head+'\nOffline latency profiling: these are recorded observations; your profiling proposals are NOT applied. Current own telemetry and shown committed controls are authoritative. Choose the next actuator plan for this recorded state.\nVisible observations:'+obs
  validate=lambda x:policy.parse(x,1,'arrival',max_duration=3)
  answer,meta=api.act(task,images,out/f'call_{i:03d}',on_ready=lambda a,m:None,validator=validate)
  try:commands=validate(answer);prediction=None;valid=True
  except (ValueError,TypeError):commands=prediction=None;valid=False
  r={'index':i,'images':len(images),'valid':valid,'commands':commands,'forecast':prediction,**meta};rows.append(r);append(out/'measurements.jsonl',r);print(json.dumps({'index':i,'valid':valid,'published':meta['published_seconds'],'full':meta['wall_seconds'],'input_tokens':meta['usage']['input_tokens']}),flush=True)
finally:api.close()
delays=[r['published_seconds'] or r['wall_seconds'] for r in rows];s={'condition':{'images':3,'chunk':1,'anchor':'arrival','schema':'actuator_array','max_duration':3,'session':True},'n':len(rows),'valid_outputs':sum(r['valid'] for r in rows),'concurrency':1,'p50':statistics.median(delays),'mean':statistics.mean(delays),'p95':max(delays),'min':min(delays),'delays':delays,'drain_delays':[r['wall_seconds'] for r in rows],'latency_endpoint':'complete legal actuator array publication','model':'gpt-6.1-sol','service_tier':'ultrafast','effort':'low','image_detail':'auto','warning':'six context-dependent samples; sample maximum is not a robust population P95'};write(out/'condition.json',s);print('CONDITION '+json.dumps(s),flush=True)
