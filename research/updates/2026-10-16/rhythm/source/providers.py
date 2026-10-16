"""Separate paid API and native subscription transports; no auth persistence."""
import asyncio,base64,json,time,uuid,pathlib,itertools
from decimal import Decimal
import httpx
from .scheduler import BudgetLedger,TokenPricing

class APIProvider:
    def __init__(self,key,output,phase='profiling',detail='high',max_output=256,effort='low',image_token_certificate=None):
        self.key=key;self.output=pathlib.Path(output);self.output.mkdir(parents=True,exist_ok=True)
        if (self.output/'budget.remote-owner.json').exists():
            raise RuntimeError('Paid calls disabled here: the cumulative budget is temporarily owned by the remote verifier')
        if not (self.output/'budget.json').is_file():
            raise RuntimeError('Existing cumulative budget.json required; refusing a fresh paid budget')
        self.phase,self.detail,self.max_output,self.effort=phase,detail,max_output,effort
        from .model_image_budget import load_certificate
        self.image_certificate=load_certificate(image_token_certificate,detail) if image_token_certificate else None
        self.ledger=BudgetLedger.existing(self.output/'budget.json');self.client=httpx.AsyncClient(timeout=60)
        self._active=set();self._closed=False
    async def act(self,prompt,images,*,on_action=None,action_validator=None):
        """Optionally deliver a complete validated plan before draining/settling.

        The caller still awaits this request through final accounting. No
        detached financial task, partial action, or timestamp repair is used.
        """
        if self._closed:raise RuntimeError('API provider is closed')
        if on_action is not None and not callable(action_validator):
            raise ValueError('Early actions require an explicit schema validator')
        task=asyncio.current_task();self._active.add(task)
        try:return await self._act(prompt,images,on_action,action_validator)
        finally:self._active.discard(task)
    async def _act(self,prompt,images,on_action,action_validator):
        call_started=time.perf_counter()
        rid=uuid.uuid4().hex;content=[{'type':'input_text','text':prompt}]+[{'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(im).decode(),'detail':self.detail} for im in images]
        payload={'model':'gpt-6.1-sol','reasoning':{'effort':self.effort},'service_tier':'ultrafast','max_output_tokens':self.max_output,'stream':True,'store':False,'text':{'verbosity':'low'},'input':[{'role':'user','content':content}]}
        # UTF-8 bytes upper-bound text tokens; each small PNG conservatively <=8192 image tokens.
        from .model_image_budget import certified_input_bound
        bound=certified_input_bound(prompt,images,self.image_certificate)
        reserve=TokenPricing('15','60').cost_usd(bound,self.max_output)
        if self.phase=='profiling':
            snap=await asyncio.to_thread(self.ledger.snapshot)
            phase_used=sum(r.get('actual_micros',r['reserved_micros']) for r in snap['requests'].values() if r['phase']==self.phase)
            if phase_used+int(reserve*1000000)>6000000:raise RuntimeError('Profiling USD6 phase ceiling')
        await asyncio.to_thread(self.ledger.reserve,rid,reserve,self.phase)
        started=time.perf_counter();first=None;response=None;text=''
        identity_ok=False;attempted=False;delivered=False;delivered_answer=None
        delivery={};callback_error=None;completion_event_s=None;cost=None
        def identity(value):
            # The created event may omit tier; verify the actual tier again
            # at completion. An explicit wrong model/tier never gets delivered.
            return value.get('model')=='gpt-6.1-sol' and value.get('service_tier') in (None,'ultrafast')
        def answer_text(value):
            return ''.join(c.get('text','') for x in value.get('output',[]) if x['type']=='message' for c in x.get('content',[]) if c['type']=='output_text')
        async def deliver(candidate,stage):
            nonlocal attempted,delivered,delivered_answer,callback_error
            if on_action is None or attempted or not identity_ok:return
            try:action_validator(candidate)
            except (ValueError,TypeError,OverflowError):return
            attempted=True;delivered_answer=candidate
            delivery.update(action_ready_s=time.perf_counter()-started,delivery_stage=stage)
            callback_started=time.perf_counter()
            try:
                await on_action(candidate,{'request_id':rid,**delivery})
                delivered=True
            except Exception as error:
                # Keep consuming usage even if the executor failed. Never retry
                # a callback whose command might already have been admitted.
                callback_error=error
            finally:delivery['action_callback_s']=time.perf_counter()-callback_started
        try:
            async with self.client.stream('POST','https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+self.key},json=payload) as res:
                if res.status_code!=200:
                    # No error bodies/headers are logged; they may contain request credentials.
                    body=await res.aread();err=json.loads(body).get('error',{});message=str(err.get('message',''))[:350].replace(self.key,'[redacted]');raise RuntimeError('API HTTP '+str(res.status_code)+' '+str(err.get('param'))+' '+message)
                async for line in res.aiter_lines():
                    if not line.startswith('data: '):continue
                    if line[6:]=='[DONE]':break
                    event=json.loads(line[6:])
                    kind=event.get('type')
                    if kind in ('response.created','response.in_progress'):
                        identity_ok=identity(event['response'])
                    if kind=='response.output_text.delta':
                        if first is None:first=time.perf_counter()-started
                        text+=event['delta']
                        # Only a complete ROOT object is eligible. Braces in
                        # strings or a finished row cannot pass the validator.
                        if text.rstrip().endswith('}'):
                            await deliver(text,'json_complete_delta')
                    if kind in ('response.completed','response.failed','response.incomplete'):
                        response=event['response'];completion_event_s=time.perf_counter()-started
                        identity_ok=identity(response) and response.get('service_tier')=='ultrafast'
                        if kind=='response.completed' and response.get('status')=='completed':
                            await deliver(answer_text(response),'completed_event')
            latency=time.perf_counter()-started
            if not response:raise RuntimeError('Missing final response')
            usage=response.get('usage') or {};i=usage['input_tokens'];o=usage['output_tokens'];details=usage.get('input_tokens_details',{});cached=details.get('cached_tokens',0);writes=details.get('cache_write_tokens',0)
            # Cache writes may overlap provider detail categories; charge pessimistically if unclear.
            cost=(Decimal(max(0,i-cached-writes))*12+Decimal(cached)*Decimal('.6')+Decimal(writes)*15+Decimal(o)*60)/1000000
            settlement_started=time.perf_counter()
            await asyncio.to_thread(self.ledger.settle,rid,cost)
            settlement_s=time.perf_counter()-settlement_started
            if response.get('model')!='gpt-6.1-sol' or response.get('service_tier')!='ultrafast':raise RuntimeError('Unexpected model/tier')
            if response.get('status')!='completed':raise RuntimeError('API response status '+str(response.get('status')))
            answer=answer_text(response)
            if delivered_answer is not None and answer.strip()!=delivered_answer.strip():
                raise RuntimeError('Final text differs from the action already offered')
            if callback_error is not None:raise callback_error
            meta={'request_id':rid,'latency_s':latency,'ttft_s':first,'usage':usage,'cost_usd':float(cost),'phase':self.phase,'model':response['model'],'tier':response['service_tier'],'detail':self.detail,'effort':self.effort,'max_output_tokens':self.max_output,'reserved_input_bound':bound,'counted_image_certificate':self.image_certificate is not None}
            meta.update(delivery,action_delivered=delivered,completion_event_s=completion_event_s)
            meta.update(pre_http_s=started-call_started,settlement_s=settlement_s,total_provider_s=time.perf_counter()-call_started)
            with (self.output/'api-requests.jsonl').open('a') as f:f.write(json.dumps({**meta,'answer':answer})+'\n')
            return answer,meta
        except BaseException as e:
            await asyncio.to_thread(self.ledger.mark_uncertain,rid,type(e).__name__)
            with (self.output/'api-requests.jsonl').open('a') as f:
                f.write(json.dumps({'request_id':rid,'phase':self.phase,'error':type(e).__name__,
                                   'action_attempted':attempted,'action_delivered':delivered,
                                   'answer':delivered_answer,'usage':response.get('usage') if response else None,
                                   'cost_usd':float(cost) if cost is not None else None,
                                   'latency_s':time.perf_counter()-started,**delivery})+'\n')
            raise
    async def close(self):
        self._closed=True
        # Early delivery must never abandon outstanding stream/accounting work.
        pending=[task for task in self._active if task is not asyncio.current_task()]
        if pending:await asyncio.gather(*pending,return_exceptions=True)
        await self.client.aclose()

class NativeProvider:
    serial=itertools.count()
    def __init__(self):self.process=None;self.lock=asyncio.Lock()
    async def start(self):
        self.process=await asyncio.create_subprocess_exec('ssh','-S',['/tmp/dfjk-research-ssh.sock','/tmp/dfjk-research-ssh-1.sock','/tmp/dfjk-research-ssh-3.sock'][next(self.serial)%3],'-o','BatchMode=yes','-o','ConnectTimeout=8','ubuntu@35.223.106.107','/home/ubuntu/lzj/envs/coding-agent-suite/bin/python -u /tmp/dfjk-remote-subscription.py',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        line=await asyncio.wait_for(self.process.stdout.readline(),90)
        if not line:
            await self.close();raise RuntimeError('Native worker exited during startup')
        ready=json.loads(line)
        if not ready.get('ready') or ready.get('auth')!='chatgpt':raise RuntimeError('Native subscription unavailable')
        return self
    async def act(self,prompt,images):
        async with self.lock:
            rid=uuid.uuid4().hex;row={'id':rid,'prompt':prompt,'images':[base64.b64encode(x).decode() for x in images]}
            self.process.stdin.write((json.dumps(row)+'\n').encode());await self.process.stdin.drain()
            result=json.loads(await asyncio.wait_for(self.process.stdout.readline(),150))
            if result.get('error'):raise RuntimeError(result['error'])
            return result['answer'],result['meta']
    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                self.process.stdin.write(b'{"op":"close"}\n');await self.process.stdin.drain()
            except (BrokenPipeError,ConnectionResetError):pass
            try:await asyncio.wait_for(self.process.wait(),15)
            except TimeoutError:self.process.terminate();await self.process.wait()
