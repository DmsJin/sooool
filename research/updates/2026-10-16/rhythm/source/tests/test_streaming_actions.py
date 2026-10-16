"""No paid calls: controllable SSE tails verify dispatch and accounting order."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.rhythm.model_compact_policy import parse
from experiments.rhythm.providers import APIProvider
from experiments.rhythm.scheduler import BudgetExceeded, BudgetLedger

ANSWER = '{"v":1,"a":[["tap","d",123.456789,273.456789]]}'


def event(kind, **data):
    return 'data: ' + json.dumps({'type': kind, **data})


def response(answer=ANSWER, status='completed', tier='ultrafast'):
    return {'model': 'gpt-6.1-sol', 'service_tier': tier, 'status': status,
            'usage': {'input_tokens': 1, 'output_tokens': 1},
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': answer}]}]}


class Client:
    def __init__(self, lines):
        self.lines = lines
        self.closed = False
        self.calls = 0

    def stream(self, *args, **kwargs):
        self.calls += 1
        lines = self.lines
        class Stream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def aiter_lines(self): return lines()
        return Stream()

    async def aclose(self): self.closed = True


class StreamingActionsTests(unittest.IsolatedAsyncioTestCase):
    def make_provider(self, tmp, client, limit='30'):
        BudgetLedger(Path(tmp)/'budget.json', limit).reserve('prior', '0', 'final')
        with patch('experiments.rhythm.providers.httpx.AsyncClient', return_value=client):
            return APIProvider('placeholder', tmp, phase='final')

    async def test_complete_root_delivered_before_terminal_eof_and_settlement_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            partial, finish_json, ready, terminal, eof = [asyncio.Event() for _ in range(5)]
            seen = []
            async def lines():
                # Tier need not be present in the response.created event.
                yield event('response.created', response={'model': 'gpt-6.1-sol'})
                yield event('response.output_text.delta', delta=ANSWER[:-1])
                partial.set()
                await finish_json.wait()
                yield event('response.output_text.delta', delta='}')
                await terminal.wait()
                yield event('response.completed', response=response())
                await eof.wait()
            async def dispatch(answer, timing):
                seen.append((answer, timing)); ready.set()
            client = Client(lines)
            provider = self.make_provider(tmp, client)
            task = asyncio.create_task(provider.act('prompt', [], on_action=dispatch, action_validator=parse))
            try:
                await asyncio.wait_for(partial.wait(), 2)
                self.assertEqual(seen, [])  # A closed row is not a closed plan.
                finish_json.set()
                await asyncio.wait_for(ready.wait(), 2)
                self.assertEqual(seen[0][0], ANSWER)
                self.assertEqual(parse(seen[0][0])['taps'][0]['at_ms'], 123.456789)
                self.assertFalse(task.done())
                record = provider.ledger.snapshot()['requests'][seen[0][1]['request_id']]
                self.assertEqual(record['state'], 'reserved')
                close = asyncio.create_task(provider.close())
                await asyncio.sleep(0)
                self.assertFalse(close.done())
                self.assertFalse(client.closed)
                terminal.set(); eof.set()
                answer, meta = await asyncio.wait_for(task, 2)
                await asyncio.wait_for(close, 2)
                self.assertEqual(answer, ANSWER)
                self.assertEqual(len(seen), 1)
                self.assertTrue(meta['action_delivered'])
                self.assertEqual(meta['delivery_stage'], 'json_complete_delta')
                self.assertLess(meta['action_ready_s'], meta['latency_s'])
                self.assertEqual(provider.ledger.snapshot()['requests'][meta['request_id']]['state'], 'settled')
                self.assertTrue(client.closed)
            finally:
                finish_json.set(); terminal.set(); eof.set()
                await asyncio.gather(task, return_exceptions=True)
                await provider.close()

    async def test_bad_or_partial_plan_never_dispatched(self):
        invalid = [ANSWER[:-1], '{"v":1,"a":[["tap","z",1,2]]}',
                   '{"v":1,"a":[["tap","d",2,1]]}',
                   '{"v":1,"a":[["same","d",1,2],["same","f",3,4]]}',
                   '{"v":true,"a":[]}',
                   '{"v":1,"a":[["brace}","d",1,2]]}']
        for text in invalid:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                async def lines():
                    yield event('response.created', response=response())
                    for chunk in text:
                        yield event('response.output_text.delta', delta=chunk)
                    yield event('response.completed', response=response(text))
                seen = []
                async def dispatch(*args): seen.append(args)
                provider = self.make_provider(tmp, Client(lines))
                try:
                    _, meta = await provider.act('p', [], on_action=dispatch, action_validator=parse)
                    self.assertEqual(seen, [])
                    self.assertFalse(meta['action_delivered'])
                    self.assertNotIn('action_ready_s', meta)
                finally: await provider.close()

    async def test_no_identity_falls_back_at_completed_event_before_eof(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready, eof = asyncio.Event(), asyncio.Event()
            seen = []
            async def lines():
                yield event('response.output_text.delta', delta=ANSWER)
                self.assertFalse(ready.is_set())
                yield event('response.completed', response=response())
                await eof.wait()
            async def dispatch(answer, timing): seen.append(timing); ready.set()
            provider = self.make_provider(tmp, Client(lines))
            task = asyncio.create_task(provider.act('p', [], on_action=dispatch, action_validator=parse))
            try:
                await asyncio.wait_for(ready.wait(), 2)
                self.assertFalse(task.done())
                self.assertEqual(seen[0]['delivery_stage'], 'completed_event')
            finally:
                eof.set(); await task; await provider.close()

    async def test_late_stream_failure_keeps_reservation_and_action_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = []
            async def lines():
                yield event('response.created', response=response())
                yield event('response.output_text.delta', delta=ANSWER)
                raise OSError('injected stream loss')
            async def dispatch(answer, timing): seen.append(timing)
            provider = self.make_provider(tmp, Client(lines))
            try:
                with self.assertRaises(OSError):
                    await provider.act('p', [], on_action=dispatch, action_validator=parse)
                self.assertEqual(len(seen), 1)
                record = provider.ledger.snapshot()['requests'][seen[0]['request_id']]
                self.assertEqual(record['state'], 'uncertain')
                self.assertGreater(record['reserved_micros'], 0)
                audit = json.loads((Path(tmp)/'api-requests.jsonl').read_text())
                self.assertTrue(audit['action_delivered'])
                self.assertEqual(audit['answer'], ANSWER)
            finally: await provider.close()

    async def test_cancellation_after_dispatch_retains_unknown_charge(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready=asyncio.Event();seen=[]
            async def lines():
                yield event('response.created',response=response())
                yield event('response.output_text.delta',delta=ANSWER)
                await asyncio.Event().wait()
            async def dispatch(answer,timing):seen.append(timing);ready.set()
            provider=self.make_provider(tmp,Client(lines))
            task=asyncio.create_task(provider.act('p',[],on_action=dispatch,action_validator=parse))
            try:
                await asyncio.wait_for(ready.wait(),2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
                self.assertEqual(len(seen),1)
                self.assertEqual(provider.ledger.snapshot()['requests'][seen[0]['request_id']]['state'],'uncertain')
            finally:
                task.cancel();await asyncio.gather(task,return_exceptions=True);await provider.close()

    async def test_final_changes_failure_status_and_executor_error_account_without_redelivery(self):
        for mode in ('different_text', 'incomplete', 'executor_error', 'wrong_tier'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                seen = []
                final = response()
                if mode == 'different_text': final = response(ANSWER + ' extra')
                if mode == 'incomplete': final = response(status='incomplete')
                if mode == 'wrong_tier': final = response(tier='default')
                async def lines():
                    yield event('response.created', response=final if mode == 'wrong_tier' else response())
                    yield event('response.output_text.delta', delta=ANSWER)
                    yield event('response.incomplete' if mode == 'incomplete' else 'response.completed', response=final)
                async def dispatch(*args):
                    seen.append(args)
                    if mode == 'executor_error': raise RuntimeError('injected executor failure')
                client = Client(lines)
                provider = self.make_provider(tmp, client)
                try:
                    with self.assertRaises(RuntimeError):
                        await provider.act('p', [], on_action=dispatch, action_validator=parse)
                    self.assertEqual(len(seen), 0 if mode == 'wrong_tier' else 1)
                    records = provider.ledger.snapshot()['requests']
                    self.assertTrue(all(x['state'] == 'settled' for x in records.values() if 'actual_micros' in x))
                    self.assertEqual(sum(x['state'] == 'settled' for k,x in records.items() if k!='prior'), 1)
                    self.assertEqual(client.calls, 1)
                finally: await provider.close()

    async def test_pending_tail_still_consumes_shared_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready, tail = asyncio.Event(), asyncio.Event()
            async def lines():
                yield event('response.created', response=response())
                yield event('response.output_text.delta', delta=ANSWER)
                await tail.wait()
                yield event('response.completed', response=response())
            async def dispatch(*args): ready.set()
            client = Client(lines)
            provider = self.make_provider(tmp, client, limit='.1')
            first = asyncio.create_task(provider.act('p', [], on_action=dispatch, action_validator=parse))
            try:
                await asyncio.wait_for(ready.wait(), 2)
                with self.assertRaises(BudgetExceeded): await provider.act('p', [])
                self.assertEqual(client.calls, 1)
            finally:
                tail.set(); await first; await provider.close()

    async def test_default_waiting_mode_and_validator_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            async def lines():
                yield event('response.created', response=response())
                yield event('response.output_text.delta', delta=ANSWER)
                yield event('response.completed', response=response())
            provider = self.make_provider(tmp, Client(lines))
            try:
                with self.assertRaises(ValueError):
                    await provider.act('p', [], on_action=lambda *a: None)
                _, meta = await provider.act('p', [])
                self.assertFalse(meta['action_delivered'])
                self.assertNotIn('action_ready_s', meta)
            finally: await provider.close()

    async def test_real_httpx_sse_fragmentation_dispatches_while_http_body_is_open(self):
        import httpx
        with tempfile.TemporaryDirectory() as tmp:
            ready, tail = asyncio.Event(), asyncio.Event()
            class Body(httpx.AsyncByteStream):
                async def __aiter__(self):
                    rows=[event('response.created',response=response()),
                          event('response.output_text.delta',delta=ANSWER[:24]),
                          event('response.output_text.delta',delta=ANSWER[24:])]
                    raw=('\n\n'.join(rows)+'\n\n').encode()
                    # SSE event lines and JSON token chunks have unrelated boundaries.
                    for i in range(0,len(raw),7):yield raw[i:i+7]
                    await tail.wait()
                    yield (event('response.completed',response=response())+'\n\n').encode()
            def handle(request):
                self.assertTrue(json.loads(request.content)['stream'])
                return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Body())
            client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
            provider=self.make_provider(tmp,client)
            async def dispatch(answer,timing):
                self.assertEqual(answer,ANSWER);ready.set()
            task=asyncio.create_task(provider.act('p',[],on_action=dispatch,action_validator=parse))
            try:
                await asyncio.wait_for(ready.wait(),3)
                self.assertFalse(task.done())
                self.assertFalse(client.is_closed)
            finally:
                tail.set();await task;await provider.close()


class NativeDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_applies_once_before_provider_finishes_and_keeps_late_error(self):
        from types import SimpleNamespace
        from experiments.rhythm.model_native import run
        for fail_tail in (False,True):
            with self.subTest(fail_tail=fail_tail), tempfile.TemporaryDirectory() as tmp:
                applied,tail=asyncio.Event(),asyncio.Event();plans=[]
                class Provider:
                    def __init__(self,*a,**kw):pass
                    async def act(self,prompt,images,**kw):
                        kw['action_validator'](ANSWER)
                        await kw['on_action'](ANSWER,{'request_id':'fake','action_ready_s':.01})
                        await tail.wait()
                        if fail_tail:raise OSError('late injected failure')
                        return ANSWER,{'latency_s':1,'action_ready_s':.01}
                    async def close(self):pass
                class Env:
                    def __init__(self,*a,**kw):pass
                    async def __aenter__(self):return self
                    async def __aexit__(self,*a):pass
                    async def start(self):pass
                    async def capture(self):return {'png':b'x','capture_start_ms':10,'capture_end_ms':10}
                    async def snapshot(self,*a):return {'clock_ms':10,'cursor':0,'pending':[],'rawacks':[],'version':0}
                    async def apply(self,plan):
                        plans.append(plan);applied.set()
                        return {'clock_ms':20,'cursor':0}
                    async def trusted_clock_diagnostic(self):return {'external_ms':10,'audio_s':0,'state':'result','paused':False,'rate':1}
                    async def trusted_evaluator(self):return {'state':'result','judged':0,'total_notes':52,'counts':{'miss':0},'max_combo':0}
                args=SimpleNamespace(lean=True,compact=True,early_actions=True,run_root=tmp,name='native-wire',
                    memory=None,chart=None,freeze=None,url='fake',browser_executable=None,audio=None,
                    detail='high',max_output=256,duration=.001,cadence=.1,concurrency=1,frames=1,max_miss=0)
                with patch('experiments.rhythm.model_native.APIProvider',Provider),patch('experiments.rhythm.model_native.ModelVisualEnv',Env):
                    task=asyncio.create_task(run(args,'placeholder'))
                    try:
                        await asyncio.wait_for(applied.wait(),2)
                        self.assertFalse(task.done())
                        self.assertEqual(plans[0]['taps'][0]['at_ms'],123.456789)
                    finally:tail.set();await task
                self.assertEqual(len(plans),1)
                row=json.loads((Path(tmp)/'model-timing/native-wire/requests.jsonl').read_text())
                self.assertIn('receipt',row)
                self.assertEqual('error' in row,fail_tail)
                self.assertIn('action_delivery',row)
