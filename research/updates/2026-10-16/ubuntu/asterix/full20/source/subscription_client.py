"""Native Codex app-server only. No API key, copied auth, or direct API requests."""
import json,pathlib,sys,time,types

class SubscriptionClient:
 def __init__(self,suite,output,quota_stop_percent=None):
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
   args.extend(['-c','model_provider="openai"','-c','forced_login_method="chatgpt"'])
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
  (output/'auth_mode.json').write_text(json.dumps({'type':'chatgpt','provider':'openai','direct_api_calls':0}))
  self.runner=runner;self.count=0;self.quota_stop_percent=quota_stop_percent
 def act(self,prompt,images,directory):
  directory.mkdir(parents=True)
  r=self.runner
  if self.quota_stop_percent is not None and self.count%25==0:
   from subscription_quota import read_limits,require_headroom
   quota=read_limits(r,directory/'quota_request.json')
   (directory/'quota_summary.json').write_text(json.dumps(quota))
   require_headroom(quota,self.quota_stop_percent)
  if self.count:
   with (directory/'thread_events.jsonl').open('w') as log:
    result,_=r._rpc('thread/start',{'model':r.settings['model'],'cwd':'/workspace','approvalPolicy':'never','sandbox':'danger-full-access','ephemeral':True},log,time.monotonic()+30,directory/'thread_request.json')
   r.thread_id=result['thread']['id']
  ims=[]
  for i,image in enumerate(images):
   path=r.workspace/'observations'/f'{self.count:05d}_{i}.png';path.write_bytes(image)
   ims.append({'path':'/workspace/observations/'+path.name})
  started=time.perf_counter();answer,result=r._request_action(prompt,ims,directory)
  self.count+=1
  # Ephemeral threads have no persisted rollout and cannot be archived.
  return answer,{'wall_seconds':time.perf_counter()-started,'token_usage':result.get('tokenUsage')}
 def close(self):self.runner.close()
