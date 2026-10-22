"""Strictly serial API profiling of unique retained task inputs; no gameplay."""
import getpass
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time


def profile(root,a):
    from runtime.run_support import freeze
    sys.path.insert(0,str(root/'environments/touhou'))
    from research.api_client import ApiClient
    from research.budget import BudgetLedger
    from research.scheduler import parse_plan
    from research.wire_schema import decision_schema
    from research.live_summary import add_brief_schema,validate_brief
    episode=a.episode.resolve();config=json.loads((episode/'config.json').read_text())
    if config.get('candidate')!='tracking_dodge_safe_intercept_v2':raise ValueError('Expected selected v2 input corpus')
    fixtures=[];seen=set()
    for d in sorted(episode.glob('decision_*')):
        if not (d/'request.json').exists():continue
        request=json.loads((d/'request.json').read_text());identity=(request['prompt_sha256'],tuple(request['image_sha256']))
        if identity in seen:continue
        seen.add(identity);prompt=(d/'prompt.txt').read_text();images=[(d/f'image_{i}.png').read_bytes() for i in range(len(request['image_sha256']))]
        if hashlib.sha256(prompt.encode()).hexdigest()!=identity[0] or tuple(hashlib.sha256(x).hexdigest() for x in images)!=identity[1]:raise ValueError('Frozen input hash mismatch')
        fixtures.append((prompt,images,request))
        if len(fixtures)>=a.max_calls:break
    if not fixtures:raise ValueError('No retained task inputs found')
    out=(a.output or root/'runs'/('touhou-profile-'+time.strftime('%Y%m%dT%H%M%S'))).resolve()
    freeze('touhou',{'policy':'tracking-safe-intercept-v2','args':config},out,mode='serial_api_profile')
    limits={'total_limit':str(a.budget_usd),'admission_limit':str(a.budget_usd),'stage_caps':{k:str(a.budget_usd) for k in ('profile','reprofile','realtime')}}
    ledger=BudgetLedger(a.ledger.resolve() if a.ledger else out/'ledger.json',**limits);before=ledger.snapshot()
    schema=decision_schema(config['candidate'],config.get('chunk_size',1),config.get('max_duration',48))
    if config.get('decision_brief'):schema=add_brief_schema(schema)
    key=os.environ.get('OPENAI_API_KEY') or getpass.getpass('OpenAI API key (process memory only): ')
    client=ApiClient(key,ledger.path,stage='profile',max_output_tokens=config.get('max_output_tokens',512),output_schema=schema,budget_limits=limits)
    samples=[]
    def validate(text):
        plan=parse_plan(text)
        if len(plan)>config.get('chunk_size',1) or any(p.duration>config.get('max_duration',48) for p in plan):raise ValueError('Action exceeds source protocol')
        if config.get('decision_brief'):validate_brief(text)
        return plan
    try:
        for i,(prompt,images,request) in enumerate(fixtures):
            d=out/f'decision_{i:05d}';d.mkdir();(d/'prompt.txt').write_text(prompt)
            for j,image in enumerate(images):(d/f'image_{j}.png').write_bytes(image)
            ready=[]
            # One blocking call at a time: terminal response and billing settle
            # before another request starts. Returned actions are never executed.
            result=client.decide(prompt,images,validate=validate,on_legal_action=lambda r:ready.append(r['meta']['legal_action_s']))
            row={'source_prompt_sha256':request['prompt_sha256'],'image_sha256':request['image_sha256'],'legal_ready_s':ready[0],'result':result}
            (d/'result.json').write_text(json.dumps(row,indent=2));samples.append(row)
    finally:
        client.close();key=None
        after=ledger.snapshot()
        (out/'accounting.json').write_text(json.dumps({'before_usd':before['committed_usd'],'after_usd':after['committed_usd'],'blocked':after['blocked']},indent=2))
    values=[s['legal_ready_s'] for s in samples]
    result={'execution_mode':'serial_api_profile','concurrency':1,'model':'gpt-6.1-sol','effort':'low','samples':len(samples),'samples_s':values,'p50_s':statistics.median(values),'complete':True,'gameplay_actions_executed':0,'won':None,'note':'Serial legal-JSON readiness on unique frozen task inputs. Not concurrent capture-to-apply calibration or gameplay acceptance. Cache usage retained per response. Small smoke samples do not characterize tails.'}
    (out/'profile.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'output':str(out),'profile':result},indent=2));return result
