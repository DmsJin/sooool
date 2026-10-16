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


def choice_json(text,count):
    """Accept only a complete single choice object; never guess an unfinished number."""
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise ValueError('Duplicate JSON key')
            result[key]=value
        return result
    try:obj=json.loads(text,object_pairs_hook=pairs)
    except (ValueError,TypeError):return None
    if not isinstance(obj,dict) or set(obj)!={'choice'} or type(obj['choice'])!=int or not 0<=obj['choice']<count:return None
    return obj


def valid_usage(usage):
    try:
        i=usage['input_tokens'];o=usage['output_tokens'];details=usage.get('input_tokens_details') or {}
        c=details.get('cached_tokens',0);w=details.get('cache_write_tokens',0)
        return all(type(v)==int and v>=0 for v in (i,o,c,w)) and c+w<=i
    except (TypeError,KeyError,AttributeError):return False

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
            except (TypeError,KeyError,ValueError,AttributeError):
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
    def call(self,items,effort='low',max_output=512,count=None,on_ready=None,choice_count=None,action_parser=None):
        if choice_count is not None and (type(choice_count)!=int or choice_count<=0):raise ValueError('Positive choice_count required')
        if choice_count is not None and action_parser is not None:raise ValueError('Choose one action contract')
        if action_parser is not None and not callable(action_parser):raise ValueError('action_parser must be callable')
        has_contract=choice_count is not None or action_parser is not None
        if on_ready is not None and not has_contract:raise ValueError('on_ready requires an action contract')
        def read_action(text):
            if action_parser is None:return choice_json(text,choice_count)
            try:return action_parser(text)
            except (ValueError,TypeError,KeyError):return None
        n=self.count(items) if count is None else count
        bound=((math.ceil(n*1.1)+128)*15+max_output*60)/1e6
        ticket=self.budget.reserve(bound,self.stage,self.stage_limit)
        data={'model':MODEL,'service_tier':TIER,'reasoning':{'effort':effort},'text':{'verbosity':'low'},
              'store':False,'stream':True,'max_output_tokens':max_output,'input':items}
        start=time.perf_counter();first=None;answer='';response=None;usage=None;error=None
        parseable=None;ready_at=None;ready_choice=None;provisional=None;terminal_at=None;terminal_kind=None
        observed={'model':None,'service_tier':None};identity_error=None
        def identity(obj):
            nonlocal identity_error
            for key,wanted in [('model',MODEL),('service_tier',TIER)]:
                value=obj.get(key)
                if value is not None:
                    observed[key]=value
                    if value!=wanted:identity_error='Unexpected streamed '+key
        def notify():
            nonlocal parseable,ready_at,ready_choice,provisional,error
            if not has_contract:return
            obj=read_action(answer)
            if obj is None:return
            if parseable is None:parseable=time.perf_counter()-start
            if ready_at is not None or identity_error:return
            ready_at=time.perf_counter()-start;ready_choice=obj
            provisional=observed['model'] is None or observed['service_tier'] is None
            if on_ready is not None:
                try:on_ready({'status':'action_ready','answer':answer,**({'choice':obj['choice']} if action_parser is None else {'action':obj}),
                              'action_ready_s':ready_at,'ttft_s':first,'model':observed['model'],
                              'tier':observed['service_tier'],'identity_provisional':provisional,
                              'requested_model':MODEL,'requested_tier':TIER})
                except Exception as exc:
                    # Callback failure invalidates this request but must not lose usage.
                    error=error or 'Readiness callback failed: '+type(exc).__name__+': '+str(exc)
        try:
            with self.http.post(self.endpoint,json=data,stream=True,timeout=(10,60)) as r:
                if r.status_code!=200:raise RuntimeError('Inference HTTP '+str(r.status_code))
                for line in r.iter_lines(chunk_size=1):
                    if not line.startswith(b'data: ') or line[6:]==b'[DONE]':continue
                    e=json.loads(line[6:]);kind=e.get('type')
                    if kind in ('response.created','response.in_progress'):
                        identity(e['response'])
                    if kind=='response.output_text.delta':
                        if first is None:first=time.perf_counter()-start
                        answer+=e['delta'];notify()
                    if kind=='response.output_text.done' and e.get('text')!=answer:
                        error=error or 'Finalized text differs from streamed text'
                    if kind=='error':error=error or 'Streaming API error'
                    if kind in ('response.completed','response.failed','response.incomplete'):
                        response=e['response'];usage=response.get('usage');terminal_at=time.perf_counter()-start;terminal_kind=kind;break
            if not response:raise RuntimeError('No terminal response')
            identity(response)
            if identity_error or response.get('model')!=MODEL or response.get('service_tier')!=TIER:
                raise RuntimeError(identity_error or 'Unexpected model or tier')
            if terminal_kind!='response.completed' or response.get('status')!='completed':raise RuntimeError('Terminal response is '+str(terminal_kind)+' / '+str(response.get('status')))
            if has_contract:
                final=read_action(answer)
                if final is None or final!=ready_choice:raise RuntimeError('Terminal action is invalid or differs from ready action')
                if 'output' in response:
                    final_text=''.join(c.get('text','') for item in response['output'] for c in item.get('content',[]) if c.get('type')=='output_text')
                    if read_action(final_text)!=final:raise RuntimeError('Terminal output differs from streamed action')
            if not valid_usage(usage):raise RuntimeError('Missing or invalid terminal usage')
        except Exception as exc:
            error=error or type(exc).__name__+': '+str(exc)
        elapsed=time.perf_counter()-start
        cost=self.budget.settle(ticket,usage)
        if cost>bound:error=error or 'Actual usage exceeded reservation'
        return {'status':response.get('status') if response else 'error','answer':answer,'error':error,
                'request_s':elapsed,'ttft_s':first,'first_parseable_s':parseable,'action_ready_s':ready_at,
                'terminal_received_s':terminal_at,'stream_tail_s':elapsed-ready_at if ready_at is not None else None,
                'identity_provisional_at_ready':provisional,'stream_model':observed['model'],'stream_tier':observed['service_tier'],
                'usage':usage,'cost_usd':cost,'model':response.get('model') if response else None,
                'tier':response.get('service_tier') if response else None}
