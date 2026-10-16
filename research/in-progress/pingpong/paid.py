"""Process-memory credential, shared reservations, no automatic retries."""
import fcntl
import json
import math
from pathlib import Path
import time
import uuid
import requests

MODEL='gpt-6.1-sol'
TIER='ultrafast'

class Budget:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
    def update(self,fn):
        with self.path.open('a+') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            f.seek(0); raw=f.read()
            d=json.loads(raw) if raw else {'limit_usd':30,'used_usd':0,'pending':{},'blocked':False}
            result=fn(d)
            f.seek(0);f.truncate();json.dump(d,f);f.flush()
            return result
    def reserve(self,amount,stage,stage_limit):
        ticket=uuid.uuid4().hex
        def fn(d):
            pending=sum(x['usd'] for x in d['pending'].values())
            staged=d.get('stages',{}).get(stage,0)+sum(x['usd'] for x in d['pending'].values() if x['stage']==stage)
            if d['blocked'] or d['used_usd']+pending+amount>27 or staged+amount>stage_limit:
                raise RuntimeError('Budget admission stopped before dispatch')
            d['pending'][ticket]={'usd':amount,'stage':stage}
        self.update(fn)
        return ticket
    def settle(self,ticket,usage):
        def fn(d):
            r=d['pending'].pop(ticket)
            try:
                i=usage['input_tokens'];o=usage['output_tokens'];details=usage.get('input_tokens_details') or {}
                c=details.get('cached_tokens',0);w=details.get('cache_write_tokens',0)
                if any(type(v)!=int or v<0 for v in (i,o,c,w)) or c+w>i:raise ValueError()
                actual=((i-c-w)*12+c*.6+w*15+o*60)/1e6
            except (TypeError,KeyError,ValueError):
                actual=r['usd'];d['blocked']=True
            if actual>r['usd']:d['blocked']=True
            d['used_usd']+=actual
            d.setdefault('stages',{}).setdefault(r['stage'],0)
            d['stages'][r['stage']]+=actual
            return actual
        return self.update(fn)

class API:
    def __init__(self,key,budget,stage,stage_limit,endpoint='https://api.openai.com/v1/responses'):
        self.http=requests.Session()
        self.http.headers.update({'Authorization':'Bearer '+key})
        self.budget=budget;self.stage=stage;self.stage_limit=stage_limit
        self.endpoint=endpoint
    def count(self,items):
        r=self.http.post('https://api.openai.com/v1/responses/input_tokens',json={'model':MODEL,'input':items},timeout=(10,30))
        if r.status_code!=200:raise RuntimeError('Token preflight HTTP '+str(r.status_code))
        n=r.json()['input_tokens']
        if type(n)!=int or not 0<n<16000:raise RuntimeError('Input size outside short-context reservation')
        return n
    def call(self,items,effort='low',max_output=512,count=None):
        n=self.count(items) if count is None else count
        bound=((math.ceil(n*1.1)+128)*15+max_output*60)/1e6
        ticket=self.budget.reserve(bound,self.stage,self.stage_limit)
        data={'model':MODEL,'service_tier':TIER,'reasoning':{'effort':effort},'text':{'verbosity':'low'},
              'store':False,'stream':True,'max_output_tokens':max_output,'input':items}
        start=time.perf_counter();first=None;answer='';response=None;usage=None;error=None
        try:
            with self.http.post(self.endpoint,json=data,stream=True,timeout=(10,60)) as r:
                if r.status_code!=200:raise RuntimeError('Inference HTTP '+str(r.status_code))
                for line in r.iter_lines(chunk_size=1):
                    if not line.startswith(b'data: ') or line[6:]==b'[DONE]':continue
                    e=json.loads(line[6:]);kind=e.get('type')
                    if kind=='response.output_text.delta':
                        if first is None:first=time.perf_counter()-start
                        answer+=e['delta']
                    if kind in ('response.completed','response.failed','response.incomplete'):
                        response=e['response'];usage=response.get('usage');break
            if not response:raise RuntimeError('No terminal response')
            if response.get('model')!=MODEL or response.get('service_tier')!=TIER:
                raise RuntimeError('Unexpected model or tier')
        except Exception as exc:
            error=type(exc).__name__+': '+str(exc)
        elapsed=time.perf_counter()-start
        cost=self.budget.settle(ticket,usage)
        return {'status':response.get('status') if response else 'error','answer':answer,'error':error,
                'request_s':elapsed,'ttft_s':first,'usage':usage,'cost_usd':cost,
                'model':response.get('model') if response else None,'tier':response.get('service_tier') if response else None}

