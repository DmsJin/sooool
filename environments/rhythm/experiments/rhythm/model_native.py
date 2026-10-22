"""Native realtime benchmark of literal model plans, without timing correction."""
import argparse,asyncio,getpass,hashlib,json,time,math
from collections import deque
from pathlib import Path
from .model_transport_env import TransportVisualEnv as ModelVisualEnv
from .model_policy import prompt,parse
from .model_profile import observation_context
from .providers import APIProvider

def acceptance(evaluator,rate_ok,drift,max_miss=0,expected_notes=52):
 complete=expected_notes>0 and evaluator['state']=='result' and evaluator['judged']==evaluator['total_notes']==expected_notes
 combo_ok=max_miss!=0 or evaluator['max_combo']==evaluator['total_notes']
 return complete,complete and evaluator['counts']['miss']<=max_miss and combo_ok and rate_ok and drift<.2

async def run(args,key):
 from . import model_compact_policy,model_lean_policy
 policy=model_lean_policy if getattr(args,'lean',False) else model_compact_policy if getattr(args,'compact',False) else None
 make_prompt,parse_plan=(policy.prompt,policy.parse) if policy else (prompt,parse)
 live_commentary=getattr(args,'live_commentary',False)
 if live_commentary:
  from .model_commentary import prompt as with_commentary
  base_prompt=make_prompt
  make_prompt=lambda context:with_commentary(base_prompt(context),getattr(args,'commentary_language','zh'))
 root=Path(args.run_root).resolve();out=root/'model-timing'/args.name
 out.mkdir(parents=True,exist_ok=False)
 memory=Path(args.memory).read_text() if args.memory else ''
 chart_bytes=Path(args.chart).read_bytes() if args.chart else None
 chart_data=json.loads(chart_bytes) if chart_bytes else None
 expected_notes=len(chart_data['notes']) if chart_data else 52
 if chart_data and chart_data['duration']!=args.duration:raise ValueError('Chart duration differs from requested episode')
 frozen=json.loads(Path(args.freeze).read_text()) if args.freeze else None
 def verify_freeze():
  if frozen:
   if args.duration != frozen['acceptance']['duration_s']:raise ValueError('Frozen duration differs')
   if args.max_miss != frozen['acceptance']['max_miss']:raise ValueError('Frozen acceptance differs')
   if any((getattr(args,k,True) if k in ('early_actions','live_commentary') else getattr(args,k))!=v for k,v in frozen['runtime'].items()):raise ValueError('Frozen runtime configuration differs')
   if hashlib.sha256(memory.encode()).hexdigest()!=frozen['memory_sha256']:raise ValueError('Frozen memory changed')
   if frozen.get('image_token_certificate_sha256'):
    if hashlib.sha256(Path(args.image_token_certificate).read_bytes()).hexdigest()!=frozen['image_token_certificate_sha256']:raise ValueError('Frozen financial certificate changed')
   for path,sha in frozen['source_sha256'].items():
    if hashlib.sha256((Path(__file__).resolve().parents[2]/path).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed: '+path)
 verify_freeze()
 provider=APIProvider(key,root,phase='final',detail=args.detail,max_output=args.max_output,image_token_certificate=getattr(args,'image_token_certificate',None))
 tasks=set();frames=[];rtts=[];rows=[];version=0
 receipt_cursor=0;receipt_tail=deque(maxlen=8)
 async def decide(context,images,framepaths):
  row={'version':context['request_version'],'observation':{k:v for k,v in context.items() if k!='frames'},'frames':framepaths,'frame_metadata':[{k:v for k,v in f.items() if k!='png'} for f in context['frames']],'prompt':make_prompt(context)}
  try:
   async def deliver(answer,delivery):
    # Validation only. All identifiers, tap times and expiry values remain
    # precisely the model's literals, including any mistakes.
    plan=parse_plan(answer)
    row.update(answer=answer,plan=plan,action_delivery=delivery)
    row['receipt']=await env.apply(plan)
    rtts.append(delivery['action_ready_s']*1000)
   async def explain(text,timing):
    row['commentary']={'text':text,'received_ms':await env.public_clock_ms(),**timing}
   answer,metadata=await provider.act(row['prompt'],images,
    on_action=deliver if getattr(args,'early_actions',True) else None,action_validator=parse_plan,
    on_commentary=explain if live_commentary else None,live_commentary=live_commentary)
   row.update(answer=answer,metadata=metadata)
   if 'receipt' not in row:
    plan=parse_plan(answer);row['plan']=plan
    row['receipt']=await env.apply(plan)
    rtts.append(metadata['latency_s']*1000)
  except Exception as error:row['error']=type(error).__name__+': '+str(error)[:200]
  rows.append(row)
  with (out/'requests.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 try:
  async with ModelVisualEnv(args.url,browser_executable=args.browser_executable,audio_path=args.audio,chart_path=args.chart,record_video_dir=None,record_sensor_dir=out/'display-frames' if getattr(args,'record_frames',False) else None) as env:
   await env.start();start=time.monotonic();next_capture=start
   diagnostics=[await env.trusted_clock_diagnostic()];next_diagnostic=start+5
   while time.monotonic()-start<args.duration+.05:
    if getattr(provider,'authentication_failed',False):break
    now=time.monotonic()
    if now<next_capture:await asyncio.sleep(min(.02,next_capture-now));continue
    next_capture=now+args.cadence
    if now>=next_diagnostic:
     diagnostics.append(await env.trusted_clock_diagnostic());next_diagnostic=now+5
    frame=await env.capture();version+=1
    framepath=f'obs-{version:04d}.png';(out/framepath).write_bytes(frame['png'])
    frames.append((frame,framepath));frames=frames[-args.frames:]
    if len(tasks)>=args.concurrency or len(rows)+len(tasks)>=getattr(args,"max_calls",1000000):continue
    snapshot=await env.snapshot(receipt_cursor)
    receipt_cursor=snapshot['cursor'];receipt_tail.extend(snapshot['rawacks'])
    snapshot['rawacks']=list(receipt_tail)
    context=observation_context([f for f,p in frames],snapshot,request_version=version,memory=memory,rtt_history_ms=rtts[-8:])
    task=asyncio.create_task(decide(context,[f['png'] for f,p in frames],[p for f,p in frames]))
    tasks.add(task);task.add_done_callback(tasks.discard)
   diagnostics.append(await env.trusted_clock_diagnostic())
   if tasks:await asyncio.gather(*list(tasks),return_exceptions=True)
   await asyncio.sleep(.3)
   verify_freeze()
   if args.chart and Path(args.chart).read_bytes()!=chart_bytes:raise ValueError('Trusted chart changed during episode')
   evaluator=await env.trusted_evaluator()
   playing_diagnostics=[d for d in diagnostics[1:] if d['state']=='playing' and not d['paused']]
   drift=max((abs((d['external_ms']-diagnostics[0]['external_ms'])/1000-(d['audio_s']-diagnostics[0]['audio_s']))for d in playing_diagnostics),default=float('inf'))
   rate_ok=all(d['rate']==1 for d in diagnostics)
   complete,passed=acceptance(evaluator,rate_ok,drift,args.max_miss,expected_notes)
   result={'complete':complete,'passed':passed,'native_clock_drift_s':drift,'policy_freeze_verified':bool(frozen),'variant':'literal_model_timing','result':evaluator,'executor':await env.snapshot(),'diagnostics':diagnostics,'requests':len(rows),'errors':sum('error'in r for r in rows),'args':vars(args)}
   (out/'result.json').write_text(json.dumps(result,indent=2))
   print('MODEL_NATIVE_RESULT '+json.dumps({k:v for k,v in result.items() if k not in ('executor','args')}),flush=True)
 finally:await provider.close()

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--url',required=True);p.add_argument('--run-root',required=True);p.add_argument('--name',required=True)
 p.add_argument('--lean',action='store_true');p.add_argument('--compact',action='store_true');p.add_argument('--freeze');p.add_argument('--memory');p.add_argument('--chart');p.add_argument('--audio');p.add_argument('--browser-executable');p.add_argument('--image-token-certificate')
 p.add_argument('--record-frames',action='store_true',help='Keep all compositor frames independently of model observation cadence')
 p.add_argument('--commentary-language',choices=('zh','en'),default='zh')
 p.add_argument('--live-commentary',action='store_true',help='Emit action then a brief public explanation in the same streamed response')
 p.add_argument('--wait-for-completion',dest='early_actions',action='store_false',help='Control: wait for the full stream and settlement before applying actions')
 p.add_argument('--cadence',type=float,default=.12);p.add_argument('--concurrency',type=int,default=20)
 p.add_argument('--frames',type=int,choices=(1,3),default=1);p.add_argument('--detail',choices=('low','high'),default='high')
 p.add_argument('--max-output',type=int,default=256)
 p.add_argument('--max-miss',type=int,default=0)
 p.add_argument('--duration',type=float,default=30.000998)
 args=p.parse_args()
 if args.max_miss<0:raise ValueError('max-miss must be nonnegative')
 if not math.isfinite(args.duration) or not 8<=args.duration<=30.001:raise ValueError('duration must be 8..30.001 seconds')
 key=getpass.getpass('API key (process memory only): ')
 asyncio.run(run(args,key))
