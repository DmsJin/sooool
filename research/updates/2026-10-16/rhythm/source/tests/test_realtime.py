"""No-network deadline tests: cancellation must not release uncertain spend."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from experiments.rhythm.realtime import request_with_deadline
from experiments.rhythm.scheduler import BudgetLedger, BudgetExceeded

class FakePaidProvider:
    def __init__(self,ledger,delay):self.ledger=ledger;self.delay=delay;self.cancelled=False
    async def act(self,text,images):
        self.ledger.reserve('fake-request','.5','final')
        try:
            await asyncio.sleep(self.delay)
            self.ledger.settle('fake-request','.01')
            return '[]',{'request_id':'fake-request'}
        except BaseException as error:
            self.cancelled=True
            self.ledger.mark_uncertain('fake-request',type(error).__name__)
            raise

class DeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_censors_but_keeps_reservation_and_event_loop_alive(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=BudgetLedger(Path(directory)/'budget.json')
            provider=FakePaidProvider(ledger,1)
            ticks=[]
            async def native_clock():
                for _ in range(3):
                    await asyncio.sleep(.002);ticks.append(1)
            clock=asyncio.create_task(native_clock())
            with self.assertRaises(TimeoutError):
                await request_with_deadline(provider,'pixels only',[b'png'],.02)
            await clock
            self.assertTrue(provider.cancelled)
            self.assertEqual(len(ticks),3)
            snapshot=ledger.snapshot()
            self.assertEqual(snapshot['committed_micros'],500000)
            self.assertEqual(snapshot['requests']['fake-request']['state'],'uncertain')

    async def test_success_settles_and_budget_rejection_is_not_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=BudgetLedger(Path(directory)/'budget.json')
            answer,meta=await request_with_deadline(FakePaidProvider(ledger,0),'',[],.1)
            self.assertEqual(answer,'[]')
            self.assertEqual(ledger.snapshot()['committed_micros'],10000)
            ledger.reserve('other-work','29.9','profiling')
            class OverBudget:
                async def act(self,text,images):ledger.reserve('over-budget','.5','final')
            with self.assertRaises(BudgetExceeded):
                await request_with_deadline(OverBudget(),'',[],.1)
            self.assertEqual(ledger.snapshot()['committed_micros'],29910000)

if __name__=='__main__':unittest.main()
