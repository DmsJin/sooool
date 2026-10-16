"""Isolated ChatGPT subscription A/B worker; task prompt/images stay verbatim.

Installed Codex 0.162.1 lacks --ignore-user-config. Both variants therefore get
an auth-only private CODEX_HOME; no shared config, AGENTS, skills or plugins are
copied. Minimal replaces the coding outer prompt using supported config fields.
Only native app-server inference is permitted; there is no API fallback.
"""
from __future__ import annotations
import argparse
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time
import types

SUITE=Path('/home/ubuntu/lzj/coding-agent-suite')
CLIENT_DIR=Path('/home/ubuntu/wzh/expts-sol/scripts/iterative-intercept-20261014')
SYSTEM_TEXT=('Follow the latest user task policy and requested output exactly.\n'
             'Use brief reasoning sufficient for a correct decision.\n'
             'Preserve necessary checks, but avoid redundant verification,\n'
             'exhaustive alternatives, or expanding the task.\n'
             'Return only the requested output, then stop.')
UNSUPPORTED=['--ignore-user-config','include_skills_usage_instructions',
             'include_plugin_usage_instructions','include_apps_usage_instructions']
MINIMAL_CONFIG={
    'developer_instructions':'','project_doc_max_bytes':0,
    'include_environment_context':False,'include_permissions_instructions':False,
    'include_collaboration_mode_instructions':False,'include_apps_instructions':False,
    'skills.include_instructions':False,'web_search':'disabled','mcp_servers':{},
    **{'features.'+key:False for key in [
        'apps','plugins','shell_tool','unified_exec','multi_agent','multi_agent_v2',
        'browser_use','browser_use_external','browser_use_full_cdp_access',
        'computer_use','image_generation','view_image','sleep_tool','goals',
        'worktrees','skill_search','skill_mcp_dependency_install',
        'workspace_dependencies','code_mode','code_mode_host','remote_plugin',
        'plugin_sharing','memories','hooks','recommended_plugins',
        'in_app_browser','in_app_chat','in_app_dictation','in_app_local_automation',
        'in_app_updates','in_app_voice','realtime_conversation','tool_suggest',
        'auth_elicitation','tool_call_mcp_elicitation']},
}

class IsolatedSubscriptionClient:
    def __init__(self,variant,output,system_text=None,model='gpt-6.1-sol',
                 effort='low',service_tier='priority',suite=SUITE,
                 auth_source=Path('/home/ubuntu/.codex/auth.json')):
        if variant not in ('baseline','minimal'):raise ValueError('Unknown outer variant')
        if variant=='minimal' and not (system_text or '').strip():raise ValueError('Nonempty user-provided system text required')
        self.variant=variant;self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True)
        self._home_dir=tempfile.TemporaryDirectory(prefix='dfjk-outer-home-')
        self.private_home=Path(self._home_dir.name);os.chmod(self.private_home,0o700)
        self._closed=False;self._client=None
        try:
            # Copy only native ChatGPT auth. The source and its rotation are never modified.
            shutil.copyfile(auth_source,self.private_home/'auth.json')
            os.chmod(self.private_home/'auth.json',0o600)
            sys.path.insert(0,str(CLIENT_DIR));sys.path.insert(0,str(Path(suite)/'code'))
            from subscription_client import SubscriptionClient
            from latency_bench.core.config import load_config
            from latency_bench.policy.codex import CodexPolicyRunner
            cfg=load_config(Path(suite)/'outputs/suite-20ep/sol-parallel-20261011T211538Z/configs/asterix_sol.yaml')
            runner=CodexPolicyRunner.__new__(CodexPolicyRunner)
            runner.settings=dict(cfg['policy'])
            runner.settings.update(codex_home=str(self.private_home),model=model,effort=effort,turn_timeout_seconds=120)
            for key in ('workspace_root','runtime_root'):
                path=self.output/key;path.mkdir(exist_ok=True);runner.settings[key]=str(path)
            runner.output=self.output/'native';runner.output.mkdir(exist_ok=True)
            runner.process=None;runner.runtime=None
            runner._archive_home=types.MethodType(lambda owner,dest:dest.mkdir(),runner)
            original_command=runner._sandbox_command
            settings={'model_provider':'openai','forced_login_method':'chatgpt','service_tier':service_tier}
            if variant=='minimal':
                system_path=self.private_home/'minimal-system.txt'
                system_path.write_text(system_text);os.chmod(system_path,0o600)
                settings.update(MINIMAL_CONFIG)
                settings['model_instructions_file']='/home/ubuntu/.codex/minimal-system.txt'
            def command(owner,workspace,runtime):
                # Preserve the original bwrap prefix, environment and mount restrictions.
                args=original_command(workspace,runtime)
                args.append('--strict-config')
                for key,value in settings.items():args.extend(['-c',key+'='+json.dumps(value)])
                return args
            runner._sandbox_command=types.MethodType(command,runner)
            original_rpc=runner._rpc
            def rpc(owner,method,params,*args,**kwargs):
                if method in ('thread/start','turn/start'):
                    params={**params,'serviceTier':service_tier}
                return original_rpc(method,params,*args,**kwargs)
            runner._rpc=types.MethodType(rpc,runner)
            client=SubscriptionClient.__new__(SubscriptionClient)
            client.runner=runner;client.count=0;client.quota_stop_percent=None
            self._client=client
            runner._start_episode(0)
            # Read account type into memory only; never retain identity or token logs.
            with io.StringIO() as events:
                result,_=runner._rpc('account/read',{'refreshToken':False},events,
                    time.monotonic()+30,self.output/'account_request.json')
            if (result.get('account') or {}).get('type')!='chatgpt':
                raise RuntimeError('Native ChatGPT subscription required; no API fallback')
            self.configuration={'variant':variant,'auth':'chatgpt','model':model,
                'effort':effort,'service_tier':service_tier,'strict_config':True,
                'private_home_permissions':'0700','auth_permissions':'0600',
                'ignore_user_config_mode':'fresh auth-only isolated home; CLI flag unsupported',
                'unsupported_flags':UNSUPPORTED,'task_prompt_modified':False,
                'system_sha256':None if variant=='baseline' else hashlib.sha256(system_text.encode()).hexdigest(),
                'minimal_config':MINIMAL_CONFIG if variant=='minimal' else {}}
            (self.output/'outer_configuration.json').write_text(json.dumps(self.configuration,indent=2))
        except BaseException:
            self.close();raise

    @property
    def runner(self):return self._client.runner
    @property
    def count(self):return self._client.count
    def act(self,prompt,images,directory):
        answer,meta=self._client.act(prompt,images,Path(directory))
        return answer,{**meta,'outer_variant':self.variant,
            'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
            'image_sha256s':[hashlib.sha256(image).hexdigest()for image in images]}
    def close(self):
        if self._closed:return
        self._closed=True
        try:
            if self._client:self._client.close()
        finally:self._home_dir.cleanup()

def build_client(variant,output,**kwargs):return IsolatedSubscriptionClient(variant,output,**kwargs)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=['baseline','minimal'],required=True)
    parser.add_argument('--system-text-file',type=Path)
    parser.add_argument('--service-tier',default='priority')
    parser.add_argument('--model',default='gpt-6.1-sol')
    parser.add_argument('--effort',default='low')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    system=args.system_text_file.read_text() if args.system_text_file else None
    out=args.output or Path(tempfile.mkdtemp(prefix='dfjk-outer-output-'))
    client=None
    def stop(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            client=build_client(args.variant,out,system_text=system,model=args.model,effort=args.effort,service_tier=args.service_tier)
        print(json.dumps({'ready':True,'auth':'chatgpt','variant':args.variant,'model':args.model,'effort':args.effort,'serviceTier':args.service_tier,'configuration':client.configuration}),flush=True)
        for line in sys.stdin:
            row=json.loads(line)
            if row.get('op')=='close':break
            if row.get('op')=='ping':
                print(json.dumps({'id':row['id'],'ok':True,'auth':'chatgpt','variant':args.variant}),flush=True);continue
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    answer,meta=client.act(row['prompt'],[base64.b64decode(value)for value in row['images']],out/('request_'+str(client.count)))
                print(json.dumps({'id':row['id'],'answer':answer,'meta':meta}),flush=True)
            except Exception as error:
                print(json.dumps({'id':row['id'],'error':type(error).__name__+': '+str(error)[:300]}),flush=True)
    finally:
        if client:client.close()

if __name__=='__main__':main()
