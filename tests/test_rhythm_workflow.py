import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from environments.rhythm import cli as rhythm_cli
from runtime.rhythm import ledger,append_record

ROOT=Path(__file__).resolve().parents[1]


class RhythmWorkflow(unittest.TestCase):
    def test_profile_uses_serial_real_provider_interface_without_browser_actions(self):
        import asyncio
        from runtime.rhythm import profile
        sys.path.insert(0,str(ROOT/'environments/rhythm'))
        active=0;calls=[]
        class Provider:
            def __init__(self,*args,**kwargs):pass
            async def act(self,text,images,*,on_action,action_validator,live_commentary):
                nonlocal active
                active+=1
                self_test.assertEqual(active,1)
                self_test.assertIn('50 ms',text)
                self_test.assertEqual(len(images),1)
                answer='{"v":1,"a":[]}'
                action_validator(answer)
                await asyncio.sleep(0)
                await on_action(answer,{'action_ready_s':1.2})
                calls.append(text);active-=1
                return answer,{'action_ready_s':1.2,'latency_s':1.3,'cost_usd':0}
            async def close(self):pass
        self_test=self
        with tempfile.TemporaryDirectory() as t:
            args=SimpleNamespace(episode=ROOT/'artifacts/rhythm/selected',output=Path(t)/'profile',ledger=None,budget_usd='1',max_calls=2)
            with patch('runtime.rhythm.credential',return_value='noncredential-test-value'),patch('experiments.rhythm.providers.APIProvider',Provider):
                result=profile(ROOT,args)
            self.assertEqual(result['samples'],2)
            self.assertEqual(len(calls),2)
            self.assertEqual(json.loads((args.output/'manifest.json').read_text())['mode'],'serial_api_profile')
            self.assertTrue((args.output/'evaluation-record.json').exists())

    def test_authentication_rejection_blocks_additional_reservations(self):
        import asyncio
        import httpx
        sys.path.insert(0,str(ROOT/'environments/rhythm'))
        from experiments.rhythm.providers import APIProvider
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);a=SimpleNamespace(ledger=None,budget_usd='1')
            book,_=ledger(ROOT,out,a)
            async def check():
                provider=APIProvider('noncredential-test-value',out,phase='final')
                await provider.client.aclose()
                requests=[]
                def reject(request):
                    requests.append(request)
                    return httpx.Response(401,json={'error':{'message':'Authentication rejected'}})
                provider.client=httpx.AsyncClient(transport=httpx.MockTransport(reject))
                try:
                    with self.assertRaisesRegex(RuntimeError,'401'):
                        await provider.act('No task',[])
                    self.assertTrue(provider.authentication_failed)
                    with self.assertRaisesRegex(RuntimeError,'authentication'):
                        await provider.act('No task',[])
                    entries=book.snapshot()['requests']
                    self.assertEqual(len(entries),1)
                    self.assertEqual(len(requests),1)
                    self.assertEqual(next(iter(entries.values()))['state'],'uncertain')
                finally:await provider.close()
            asyncio.run(check())

    def test_paid_eval_requires_budget_before_any_provider(self):
        for value in [None,'NaN','-1']:
            args=['sol','eval','rhythm']+(['--budget-usd',value] if value else [])
            with patch.object(sys,'argv',args),patch('runtime.rhythm.evaluate') as run:
                with self.assertRaises(SystemExit):rhythm_cli.main([sys.argv[1], *sys.argv[3:]])
                run.assert_not_called()

    def test_real_eval_dispatch_does_not_run_simulation(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'run'
            with patch.object(sys,'argv',['sol','eval','rhythm','--budget-usd','1','--output',str(out)]),patch('runtime.rhythm.evaluate',return_value={}) as live,patch('runtime.rhythm.simulate') as sim:
                rhythm_cli.main([sys.argv[1], *sys.argv[3:]])
            live.assert_called_once();sim.assert_not_called()
            self.assertEqual(json.loads((out/'manifest.json').read_text())['mode'],'realtime_api')

    def test_shared_ledger_symlinks_keep_one_lock_and_retained_reservation(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);a=SimpleNamespace(ledger=p/'shared.json',budget_usd='5')
            for name in ['one','two']:(p/name).mkdir()
            first,_=ledger(ROOT,p/'one',a)
            first.reserve('unknown','1','final');first.mark_uncertain('unknown','transport lost')
            second,before=ledger(ROOT,p/'two',a)
            self.assertEqual(before['committed_micros'],1000000)
            from experiments.rhythm.scheduler import BudgetLedger
            reopened=BudgetLedger.existing(p/'two/budget.json')
            self.assertEqual(first.path,reopened.path)
            reopened.reserve('new','1','final')
            self.assertEqual(first.snapshot()['committed_micros'],2000000)
            self.assertTrue((p/'two/budget.json').is_symlink())

    def test_record_append_is_idempotent_and_rejects_changed_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);run=p/'run';run.mkdir();f=run/'evaluation-record.json'
            f.write_text(json.dumps({'game':'rhythm','mode':'realtime_api','summary':{'miss':0}}))
            registry=p/'registry.jsonl'
            self.assertTrue(append_record(run,registry));self.assertFalse(append_record(run,registry))
            f.write_text(json.dumps({'game':'rhythm','mode':'realtime_api','summary':{'miss':1}}))
            with self.assertRaises(ValueError):append_record(run,registry)

    def test_selected_policy_and_literal_receipts_match_historical_result(self):
        sys.path.insert(0,str(ROOT/'environments/rhythm'))
        from experiments.rhythm.model_lean_policy import parse
        run=ROOT/'artifacts/rhythm/selected'
        result=json.loads((run/'result.json').read_text())
        self.assertEqual(result['result']['counts'],{'perfect':24,'great':1,'ok':0,'miss':0})
        self.assertEqual(result['result']['empty_presses'],2)
        self.assertFalse(result['passed'])
        import hashlib
        memory=ROOT/'policies/rhythm/v21/memory.txt'
        self.assertEqual(hashlib.sha256(memory.read_bytes()).hexdigest(),result['memory_sha256'])
        for line in (run/'requests.jsonl').read_text().splitlines():
            row=json.loads(line)
            self.assertEqual(parse(row['answer']),row['plan'])
            for name in row['frames']:self.assertTrue((run/name).exists())
