import tempfile
from pathlib import Path
import unittest
from paid import Budget

class BudgetTests(unittest.TestCase):
    def test_pending_reservations_share_the_total_limit(self):
        with tempfile.TemporaryDirectory() as d:
            a=Budget(Path(d)/'ledger.json'); b=Budget(Path(d)/'ledger.json')
            a.reserve(20,'validation',25)
            with self.assertRaises(RuntimeError):b.reserve(8,'validation',25)
            self.assertEqual(a.update(lambda x:len(x['pending'])),1)
    def test_unknown_charge_keeps_full_cost_and_blocks_new_requests(self):
        with tempfile.TemporaryDirectory() as d:
            b=Budget(Path(d)/'ledger.json');t=b.reserve(.2,'profiling',5)
            self.assertEqual(b.settle(t,None),.2)
            with self.assertRaises(RuntimeError):b.reserve(.01,'profiling',5)
    def test_cache_accounting_and_stage_ceiling(self):
        with tempfile.TemporaryDirectory() as d:
            b=Budget(Path(d)/'ledger.json');t=b.reserve(.1,'profiling',5)
            cost=b.settle(t,{'input_tokens':1000,'output_tokens':2,'input_tokens_details':{'cached_tokens':600,'cache_write_tokens':100}})
            self.assertAlmostEqual(cost,.00558)
            with self.assertRaises(RuntimeError):b.reserve(5,'profiling',5)

if __name__=='__main__':unittest.main()
