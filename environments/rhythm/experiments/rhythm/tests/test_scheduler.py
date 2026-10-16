import multiprocessing
import tempfile
import unittest
from pathlib import Path

from experiments.rhythm.scheduler import BudgetExceeded, BudgetLedger, TokenPricing


def reserve_worker(path, result):
    try:
        BudgetLedger(path).reserve(str(multiprocessing.current_process().pid), '10', 'parallel')
        result.put(True)
    except BudgetExceeded:
        result.put(False)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'budget.json'

    def test_explicit_budget_increase_preserves_uncertain_charges(self):
        ledger = BudgetLedger(self.path, '40')
        ledger.reserve('prior', '29.858904', 'final')
        ledger.mark_uncertain('prior', 'unknown billing retained')
        reopened = BudgetLedger.existing(self.path)
        self.assertEqual(reopened.snapshot()['remaining_micros'], 10_141_096)
        reopened.reserve('new', '10', 'final')
        with self.assertRaises(BudgetExceeded):
            reopened.reserve('over', '.141097', 'final')
        with self.assertRaisesRegex(ValueError, 'USD 80'):
            BudgetLedger(self.path, '80.000001')

    def test_latest_increment_covers_profiling_and_final_together(self):
        ledger=BudgetLedger(self.path,'49.886709')
        ledger.reserve('all_prior','39.896709','prior')
        ledger.mark_uncertain('all_prior','Prior reservations retained')
        ledger.reserve('profile','.99','profiling')
        ledger.reserve('final','9','final')
        self.assertEqual(ledger.snapshot()['remaining_micros'],0)
        with self.assertRaises(BudgetExceeded):
            ledger.reserve('over','.000001','final')

    def test_all_phases_and_uncertain_retries_share_ceiling(self):
        l = BudgetLedger(self.path)
        l.reserve('profile', '6', 'profiling')
        l.reserve('final', '20', 'final')
        l.mark_uncertain('final', 'transport timeout; usage unknown')
        l.reserve('retry', '4', 'retry')
        with self.assertRaises(BudgetExceeded):
            l.reserve('extra', '.000001', 'final')
        self.assertEqual(BudgetLedger(self.path).snapshot()['remaining_micros'], 0)
        l.settle('profile', '2')
        self.assertEqual(l.snapshot()['remaining_micros'], 4_000_000)

    def test_rounding_up_and_uncached_pricing(self):
        l = BudgetLedger(self.path)
        l.reserve('tiny', '0.00000001', 'profile')
        self.assertEqual(l.snapshot()['committed_micros'], 1)
        self.assertEqual(str(TokenPricing('2', '10').cost_usd(1000, 200)), '0.004')

    def test_underestimate_records_true_cost_and_halts(self):
        l = BudgetLedger(self.path)
        l.reserve('r', '1', 'profile')
        with self.assertRaises(BudgetExceeded):
            l.settle('r', '2')
        self.assertEqual(l.snapshot()['committed_micros'], 2_000_000)
        with self.assertRaises(BudgetExceeded):
            l.reserve('next', '.1', 'profile')

    def test_settlement_idempotence_and_no_retry_id_reuse(self):
        l = BudgetLedger(self.path)
        l.reserve('r', '1', 'profile')
        l.settle('r', '.5')
        l.settle('r', '.5')
        with self.assertRaises(ValueError):
            l.settle('r', '.6')
        with self.assertRaises(ValueError):
            l.reserve('r', '.1', 'retry')

    def test_process_safe_reservations(self):
        context = multiprocessing.get_context('fork')
        result = context.Queue()
        workers = [context.Process(target=reserve_worker, args=(str(self.path), result)) for _ in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(10)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(sum(result.get(timeout=2) for _ in workers), 3)
        self.assertEqual(BudgetLedger(self.path).snapshot()['committed_micros'], 30_000_000)


if __name__ == '__main__':
    unittest.main()
