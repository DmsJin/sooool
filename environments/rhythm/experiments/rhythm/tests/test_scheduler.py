import multiprocessing
import tempfile
import unittest
from pathlib import Path

from experiments.rhythm.scheduler import ActionScheduler, BudgetExceeded, BudgetLedger, TokenPricing


def reserve_worker(path, result):
    try:
        BudgetLedger(path).reserve(str(multiprocessing.current_process().pid), '10', 'parallel')
        result.put(True)
    except BudgetExceeded:
        result.put(False)


class SchedulerTests(unittest.TestCase):
    def test_causal_activation_and_pending_invisible(self):
        s = ActionScheduler()
        self.assertEqual(s.advance(100), [])  # No plan for a pending request.
        accepted = s.submit('r1', 0, [[0, 90], [1, 120]], 110)
        self.assertEqual([a.lane for a in accepted], [1])
        self.assertEqual(s.advance(119), [])
        self.assertEqual([a.lane for a in s.advance(120)], [1])
        self.assertEqual(s.rejected_late, 1)

    def test_out_of_order_answer_cannot_replace_newer_observation(self):
        s = ActionScheduler()
        s.submit('new', 100, [[0, 200]], 150, horizon_ms=300)
        s.submit('old', 0, [[0, 250]], 200, horizon_ms=400)
        self.assertEqual(s.rejected_stale, 1)
        self.assertEqual([(a.request_id, a.game_ms) for a in s.advance(300)], [('new', 300)])

    def test_fresh_plan_cancels_overlap_but_preserves_other_lanes(self):
        s = ActionScheduler()
        s.submit('old', 0, [[0, 300], [1, 300], [0, 600]], 0)
        s.submit('new', 100, [[0, 250]], 150, horizon_ms=300)
        self.assertEqual([(a.lane, a.game_ms) for a in s.advance(400)], [(1, 300), (0, 350)])
        self.assertEqual([(a.lane, a.game_ms) for a in s.advance(600)], [(0, 600)])

    def test_empty_correction_and_duplicate_event(self):
        s = ActionScheduler()
        s.submit('old', 0, [[0, 100], [0, 100]], 0)
        self.assertEqual(len(s.advance(100)), 1)
        s.submit('again', 100, [[0, 0]], 100)
        self.assertEqual(s.advance(100), [])
        s.submit('future', 100, [[1, 100]], 100)
        s.submit('cancel', 150, [], 150, horizon_ms=100, lanes=[1])
        self.assertEqual(s.advance(200), [])
        with self.assertRaises(ValueError):
            s.advance(199)

    def test_future_activation_never_executes_early(self):
        s = ActionScheduler()
        s.submit('r', 0, [[0, 120]], 110)
        self.assertEqual(s.advance(109), [])
        self.assertEqual(s.advance(119), [])
        self.assertEqual(len(s.advance(120)), 1)

    def test_pending_snapshot_and_refractory_replan(self):
        s = ActionScheduler()
        s.submit('first', 0, [[0, 100]], 0)
        self.assertEqual([(a.lane, a.game_ms) for a in s.pending()], [(0, 100)])
        self.assertEqual(len(s.advance(100)), 1)
        self.assertEqual(s.pending(), [])
        s.submit('replan', 100, [[0, 100], [0, 265]], 110)
        self.assertEqual(s.rejected_refractory, 1)
        self.assertEqual([a.game_ms for a in s.pending()], [365])
        self.assertEqual(len(s.advance(365)), 1)

    def test_refractory_uses_actual_execution_tick_and_is_configurable(self):
        s = ActionScheduler(executed_refractory_ms=160)
        s.submit('first', 0, [[0, 100]], 0)
        s.advance(150)
        s.submit('next', 150, [[0, 120]], 160)
        self.assertEqual(s.pending(), [])  # 270 - actual execution 150 < 160.
        s = ActionScheduler(executed_refractory_ms=0)
        s.submit('first', 0, [[0, 100], [0, 200]], 0)
        self.assertEqual(len(s.advance(100)), 1)
        self.assertEqual(len(s.advance(200)), 1)

    def test_browser_acknowledgement_removes_pending_and_starts_refractory(self):
        s = ActionScheduler()
        s.submit('first', 0, [[0, 100], [1, 100]], 0)
        s.acknowledge(0, 100, 105)
        self.assertEqual([a.lane for a in s.pending()], [1])
        s.submit('replan', 105, [[0, 100], [0, 265]], 110)
        self.assertEqual(s.rejected_refractory, 1)
        self.assertEqual([(a.lane, a.game_ms) for a in s.pending()], [(1, 100), (0, 370)])
        # Idempotent delayed log delivery cannot move the clock backwards.
        s.acknowledge(0, 100, 105)
        s.acknowledge(1, 100, 102)
        self.assertEqual(s.game_ms, 105)

    def test_expired_browser_entry_has_no_refractory_and_stale_ack_preserves_newer(self):
        s = ActionScheduler()
        s.submit('first', 0, [[0, 100]], 0)
        s.acknowledge(0, 100, 200, executed=False)
        self.assertEqual(s.pending(), [])
        s.submit('next', 200, [[0, 10]], 200)
        self.assertEqual(len(s.pending()), 1)
        s.acknowledge(0, 210, 215)
        s.acknowledge(0, 50, 55)
        self.assertEqual(s.game_ms, 215)
        s.submit('near', 215, [[0, 100]], 220)
        self.assertEqual(s.pending(), [])

    def test_acknowledgement_float_roundtrip_tolerance_is_narrow(self):
        s = ActionScheduler()
        original = next(i / 37 for i in range(100000) if (i / 37) / 1000 * 1000 != i / 37)
        roundtripped = original / 1000 * 1000
        self.assertNotEqual(original, roundtripped)
        s.submit('first', 0, [[0, original], [1, original]], 0)
        s.acknowledge(0, roundtripped, original + 1)
        self.assertEqual([a.lane for a in s.pending()], [1])
        s.acknowledge(1, original + 2e-6, original + 2)
        self.assertEqual([a.lane for a in s.pending()], [1])
        s.acknowledge(1, original + .5e-6, original + 3)
        self.assertEqual(s.pending(), [])

    def test_first_miss_trajectory_optional_commit_guard(self):
        for guard, retained in ((0, False), (50, True)):
            with self.subTest(guard_ms=guard):
                s = ActionScheduler(commit_guard_ms=guard)
                s.submit('old', 5550, [[2, 7080.449251 - 5550]], 6778.493,
                         horizon_ms=1800, lanes=[0, 1, 2, 3])
                s.advance(7078.382001)
                s.submit('new', 5850, [[2, 7077.953411 - 5850]], 7078.382001,
                         horizon_ms=1800, lanes=[0, 1, 2, 3])
                self.assertEqual(s.rejected_late, 1)
                self.assertEqual(bool(s.pending()), retained)
                if retained:
                    self.assertEqual(s.pending()[0].game_ms, 7080.449251)
                    self.assertEqual(len(s.advance(7080.449251)), 1)

    def test_commit_guard_freezes_near_hit_and_rejects_near_duplicate(self):
        s = ActionScheduler(commit_guard_ms=50)
        s.submit('old', 0, [[0, 300], [1, 300]], 0)
        s.advance(270)
        s.submit('new', 100, [[0, 210], [0, 465]], 270, horizon_ms=600,
                 lanes=[0, 1, 2, 3])
        self.assertEqual(s.rejected_committed, 1)
        self.assertEqual([(a.lane, a.game_ms) for a in s.pending()], [(0, 300), (1, 300), (0, 565)])
        self.assertEqual(len(s.advance(300)), 2)
        self.assertEqual(len(s.advance(565)), 1)

    def test_commit_guard_does_not_freeze_far_future_or_accept_negative(self):
        s = ActionScheduler(commit_guard_ms=50)
        s.submit('old', 0, [[0, 400]], 0)
        s.submit('cancel', 100, [], 200, horizon_ms=500, lanes=[0])
        self.assertEqual(s.pending(), [])
        with self.assertRaises(ValueError):
            ActionScheduler(commit_guard_ms=-1)


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
        with self.assertRaisesRegex(ValueError, 'USD 49.886709'):
            BudgetLedger(self.path, '49.886710')

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
