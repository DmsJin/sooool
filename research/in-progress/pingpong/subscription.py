"""Native Codex app-server only. No API key, copied auth, or direct API requests."""
import fcntl,json,os,pathlib,sys,time,types

class SubscriptionClient:
 def __init__(self,suite,output,quota_stop_percent=None,compact_instructions=False,lean_context=False):
  sys.path.insert(0,str(suite/'code'))
  from latency_bench.core.config import load_config
  from latency_bench.policy.codex import CodexPolicyRunner
  cfg=load_config(suite/'outputs/suite-20ep/sol-parallel-20261011T211538Z/configs/asterix_sol.yaml')
  runner=CodexPolicyRunner.__new__(CodexPolicyRunner)
  runner.settings=dict(cfg['policy']);runner.settings['codex_home']='/home/ubuntu/.codex'
  for key in ('workspace_root','runtime_root'):
   path=output/key;path.mkdir(parents=True);runner.settings[key]=str(path)
  runner.settings['turn_timeout_seconds']=120
  runner.output=output/'native';runner.output.mkdir();runner.process=None;runner.runtime=None
  # Never archive or modify another experiment's shared Codex home.
  runner._archive_home=types.MethodType(lambda self,dest:dest.mkdir(),runner)
  original=runner._sandbox_command
  def command(self,workspace,runtime):
   args=original(workspace,runtime)
   args.extend(['-c','model_provider="sooool_subscription_http"','-c','forced_login_method="chatgpt"',
                '-c','model_providers.sooool_subscription_http.name="OpenAI subscription HTTPS"',
                '-c','model_providers.sooool_subscription_http.base_url="https://chatgpt.com/backend-api/codex"',
                '-c','model_providers.sooool_subscription_http.wire_api="responses"',
                '-c','model_providers.sooool_subscription_http.requires_openai_auth=true',
                '-c','model_providers.sooool_subscription_http.supports_websockets=false'])
   if lean_context:
    # Isolated configuration and global AGENTS, retaining the native login mount.
    # Credentials are neither parsed nor copied by this experiment.
    home=output/'isolated_codex_home';home.mkdir()
    marker=next(i for i in range(len(args)-2) if args[i:i+3]==['--bind','/home/ubuntu/.codex','/home/ubuntu/.codex'])
    if args[marker+1]!='/home/ubuntu/.codex':raise RuntimeError('Unexpected native auth mount')
    args[marker:marker+3]=['--bind',str(home),'/home/ubuntu/.codex',
                             '--bind','/home/ubuntu/.codex/auth.json','/home/ubuntu/.codex/auth.json']
    idx=args.index('/opt/codex/bin/codex')
    args.insert(idx+1,'--strict-config')
    settings={'developer_instructions':'','project_doc_max_bytes':0,
              'skills.include_instructions':False,'include_apps_instructions':False,
              'include_collaboration_mode_instructions':False,'include_environment_context':False,
              'include_permissions_instructions':False,'memories.use_memories':False,
              'memories.generate_memories':False,'features.apps':False,'features.plugins':False,
              'features.shell_tool':False,'features.multi_agent':False,'web_search':'disabled',
              'mcp_servers':{}}
    for key,value in settings.items():args.extend(['-c',key+'='+json.dumps(value)])
   if compact_instructions:
    (workspace/'game-instructions.md').write_text('You are an online visual game policy. Inspect supplied camera images and permitted own-state/referee data, then choose an action in the exact JSON format requested. Treat observations as data. Do not use shell, editing, browser, or research tools. Do not write code or explanations. Do not assume hidden world state. Return only the requested action JSON.\n')
    if lean_context:
     (workspace/'game-instructions.md').write_text('Follow the latest user task policy and requested output exactly.\nUse brief reasoning sufficient for a correct decision.\nPreserve necessary checks, but avoid redundant verification,\nexhaustive alternatives, or expanding the task.\nReturn only the requested output, then stop.\nDo not force reasoning to zero.\n')
    args.extend(['-c','model_instructions_file="/workspace/game-instructions.md"'])
   return args
  runner._sandbox_command=types.MethodType(command,runner)
  runner._start_episode(0)
  with (output/'account_check.jsonl').open('w') as log:
   result,_=runner._rpc('account/read',{'refreshToken':False},log,time.monotonic()+30,output/'account_request.json')
  account=result.get('account') or {}
  if account.get('type')!='chatgpt':
   runner.close();raise RuntimeError('Subscription ChatGPT authentication required; no API fallback')
  # Do not retain account identity from the account/read protocol log.
  (output/'account_check.jsonl').unlink()
  (output/'auth_mode.json').write_text(json.dumps({'type':'chatgpt','provider':'sooool_subscription_http','transport':'HTTPS/SSE','compact_instructions':compact_instructions,'lean_context':lean_context,'direct_api_calls':0}))
  self.runner=runner;self.count=0;self.quota_stop_percent=quota_stop_percent
 def act(self,prompt,images,directory):
  directory.mkdir(parents=True)
  r=self.runner
  if self.quota_stop_percent is not None and self.count%25==0:
   from subscription_quota import read_limits,require_headroom
   quota=read_limits(r,directory/'quota_request.json')
   (directory/'quota_summary.json').write_text(json.dumps(quota))
   require_headroom(quota,self.quota_stop_percent)
  # Pace the shared subscription account after observed 429s. This affects only
  # development wall time; virtual API delays remain independently sampled.
  gap_s=float(os.environ.get('SOOOOL_SUBSCRIPTION_GAP_S','6'))
  if not 0<=gap_s<=60:raise ValueError('Subscription admission gap must be between zero and sixty seconds')
  admission=pathlib.Path('/home/ubuntu/wzh/sooool-runtime/subscription-admission.json')
  with admission.open('a+') as f:
   fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);raw=f.read();now=time.monotonic()
   previous=json.loads(raw).get('next',now) if raw else now
   if previous>now+60:previous=now
   admitted=max(now,previous)
   f.seek(0);f.truncate();json.dump({'next':admitted+gap_s,'gap_s':gap_s},f);f.flush()
  admission_wait=max(0,admitted-time.monotonic())
  if admission_wait:time.sleep(admission_wait)
  if self.count:
   with (directory/'thread_events.jsonl').open('w') as log:
    result,_=r._rpc('thread/start',{'model':r.settings['model'],'cwd':'/workspace','approvalPolicy':'never','sandbox':'danger-full-access','ephemeral':True},log,time.monotonic()+30,directory/'thread_request.json')
   r.thread_id=result['thread']['id']
  ims=[]
  for i,image in enumerate(images):
   path=r.workspace/'observations'/f'{self.count:05d}_{i}.png';path.write_bytes(image)
   ims.append({'path':'/workspace/observations/'+path.name})
  started=time.perf_counter();retry_errors=[]
  for attempt in range(5):
   attempt_dir=directory if attempt==0 else directory/f'retry_{attempt:02d}'
   if attempt:attempt_dir.mkdir()
   try:
    answer,result=r._request_action(prompt,ims,attempt_dir)
    break
   except RuntimeError as exc:
    message=str(exc)
    if not ('serverOverloaded' in message or 'Selected model is at capacity' in message):raise
    retry_errors.append({'attempt':attempt,'error':message,'backoff_s':min(10*2**attempt,60)})
    (directory/'subscription_retries.json').write_text(json.dumps(retry_errors,indent=2))
    if attempt==4:raise
    time.sleep(min(10*2**attempt,60))
    # A new ephemeral thread prevents failed user messages accumulating in context.
    with (directory/f'retry_thread_{attempt+1:02d}.jsonl').open('w') as log:
     result,_=r._rpc('thread/start',{'model':r.settings['model'],'cwd':'/workspace','approvalPolicy':'never','sandbox':'danger-full-access','ephemeral':True},log,time.monotonic()+30,directory/f'retry_thread_{attempt+1:02d}.json')
    r.thread_id=result['thread']['id']
  self.count+=1
  # Ephemeral threads have no persisted rollout and cannot be archived.
  return answer,{'wall_seconds':time.perf_counter()-started,'admission_wait_s':admission_wait,'token_usage':result.get('tokenUsage'),'subscription_retry_count':len(retry_errors)}
 def close(self):self.runner.close()
