import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch

from experiments.rhythm.providers import APIProvider
from experiments.rhythm.scheduler import BudgetLedger
from experiments.rhythm.model_token_preflight import run as preflight


class SnapshotTests(unittest.TestCase):
    def test_snapshot_does_not_write_existing_or_create_fresh_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'budget.json'
            ledger = BudgetLedger(path)
            with patch('experiments.rhythm.scheduler.os.fsync') as fsync:
                self.assertEqual(ledger.snapshot()['remaining_micros'], 30_000_000)
                fsync.assert_not_called()
            self.assertFalse(path.exists())
            ledger.reserve('existing', '1', 'final')
            before, stat = path.read_bytes(), path.stat()
            with patch('experiments.rhythm.scheduler.os.fsync') as fsync:
                self.assertEqual(ledger.snapshot()['committed_micros'], 1_000_000)
                fsync.assert_not_called()
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(path.stat().st_mtime_ns, stat.st_mtime_ns)
            self.assertEqual(path.stat().st_ino, stat.st_ino)

    def test_readonly_snapshot_still_validates_authorized_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'budget.json'
            path.write_text(json.dumps({'version':1,'limit_micros':31_000_000,'requests':{}}))
            with self.assertRaisesRegex(ValueError,'limit differs'):
                BudgetLedger(path).snapshot()


class ProviderIOTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_budget_rejected_before_client_or_preflight_input_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('experiments.rhythm.providers.httpx.AsyncClient') as client:
                with self.assertRaisesRegex(RuntimeError, 'Existing cumulative'):
                    APIProvider('placeholder', tmp)
                client.assert_not_called()
            args=SimpleNamespace(run_root=tmp,output=str(Path(tmp)/'certificate.json'),image='missing-image')
            with patch('experiments.rhythm.model_token_preflight.httpx.AsyncClient') as client:
                with self.assertRaisesRegex(RuntimeError, 'Existing cumulative'):
                    await preflight(args,'placeholder')
                client.assert_not_called()
            self.assertFalse((Path(tmp)/'budget.json').exists())

    async def test_reservation_durable_before_http_and_settlement_before_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'budget.json'
            BudgetLedger(path).reserve('prior','0','final')
            started, release = threading.Event(), threading.Event()
            calls=[]
            main_thread=threading.get_ident()
            response={'model':'gpt-6.1-sol','service_tier':'ultrafast','status':'completed',
                      'usage':{'input_tokens':1,'output_tokens':1},
                      'output':[{'type':'message','content':[{'type':'output_text','text':'literal-answer'}]}]}
            class Stream:
                status_code=200
                async def __aenter__(self):return self
                async def __aexit__(self,*a):pass
                async def aiter_lines(self):
                    yield 'data: '+json.dumps({'type':'response.completed','response':response})
            class Client:
                def stream(self,*a,**kw):
                    records=BudgetLedger(path).snapshot()['requests']
                    self.asserted=True
                    if not any(k!='prior' and v['state']=='reserved' for k,v in records.items()):
                        raise AssertionError('HTTP before durable reservation')
                    calls.append('HTTP');return Stream()
                async def aclose(self):pass
            with patch('experiments.rhythm.providers.httpx.AsyncClient',return_value=Client()):
                provider=APIProvider('placeholder',tmp,phase='final')
            original_reserve,original_settle=provider.ledger.reserve,provider.ledger.settle
            def gated_reserve(*a):
                self.assertNotEqual(threading.get_ident(),main_thread)
                started.set()
                if not release.wait(3):raise AssertionError('test gate timeout')
                return original_reserve(*a)
            def threaded_settle(*a):
                self.assertNotEqual(threading.get_ident(),main_thread)
                calls.append('settle');return original_settle(*a)
            provider.ledger.reserve=gated_reserve
            provider.ledger.settle=threaded_settle
            task=asyncio.create_task(provider.act('prompt',[]))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait,2))
                self.assertEqual(calls,[])
                self.assertFalse(task.done())
                self.assertEqual(set(BudgetLedger(path).snapshot()['requests']),{'prior'})
                release.set()
                answer,meta=await asyncio.wait_for(task,3)
                self.assertEqual(answer,'literal-answer')
                self.assertEqual(calls,['HTTP','settle'])
                self.assertEqual(BudgetLedger(path).snapshot()['requests'][meta['request_id']]['state'],'settled')
            finally:
                release.set()
                await provider.close()
