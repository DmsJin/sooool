import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from research.budget import BudgetError, BudgetLedger, reservation_usd, usage_usd
from research.api_client import ApiClient
from research.profile_api import legal_action


def reserve_worker(path, queue):
    try:
        ledger = BudgetLedger(path)
        rid = ledger.reserve("profile", "1")
        ledger.settle(rid, "1")
        queue.put(True)
    except BudgetError:
        queue.put(False)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "ledger.json")
        self.ledger = BudgetLedger(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_explicit_limit_reserves_inflight_with_no_extra_padding(self):
        ledger=BudgetLedger(self.path,total_limit=35,admission_limit=35,
                            stage_caps={'profile':6,'reprofile':3,'realtime':35})
        rid=ledger.reserve('realtime',34)
        ledger.settle(rid,34)
        ledger.reserve('realtime',1)
        with self.assertRaises(BudgetError):ledger.reserve('realtime','.01')
        self.assertEqual(ledger.snapshot()['committed_usd'],'35')

    def test_invalid_limits_fail_before_creating_ledger(self):
        for values in ({'total_limit':30,'admission_limit':35},
                       {'total_limit':'NaN'}, {'stage_caps':{'realtime':35}}):
            with self.assertRaises(BudgetError):BudgetLedger(self.path,**values)
        self.assertFalse(Path(self.path).exists())

    def test_cross_process_stage_cap(self):
        queue = multiprocessing.Queue()
        processes = [multiprocessing.Process(target=reserve_worker, args=(self.path, queue)) for _ in range(12)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sum(queue.get(timeout=2) for _ in processes), 6)
        self.assertEqual(self.ledger.snapshot()["committed_usd"], "6")

    def test_abandoned_inflight_blocks_restart(self):
        rid = self.ledger.reserve("profile", ".1")
        state = json.loads(Path(self.path).read_text())
        state["requests"][rid]["owner_start"] = "not-the-current-process"
        Path(self.path).write_text(json.dumps(state))
        with self.assertRaises(BudgetError):
            BudgetLedger(self.path).reserve("profile", ".01")
        self.assertEqual(self.ledger.snapshot()["requests"][rid]["status"], "unknown")

    def test_total_cap_counts_all_inflight(self):
        self.ledger.reserve("profile", 6)
        self.ledger.reserve("reprofile", 3)
        self.ledger.reserve("realtime", 18)
        with self.assertRaises(BudgetError):
            self.ledger.reserve("realtime", ".01")
        self.assertEqual(self.ledger.snapshot()["committed_usd"], "27")

    def test_unknown_usage_blocks_restart(self):
        rid = self.ledger.reserve("profile", ".1")
        self.ledger.unknown(rid, "disconnected")
        restarted = BudgetLedger(self.path)
        self.assertEqual(restarted.snapshot()["committed_usd"], "0.1")
        with self.assertRaises(BudgetError):
            restarted.reserve("profile", ".01")

    def test_overrun_persisted_and_blocks(self):
        rid = self.ledger.reserve("profile", ".1")
        with self.assertRaises(BudgetError):
            self.ledger.settle(rid, ".11")
        self.assertEqual(self.ledger.snapshot()["committed_usd"], "0.11")
        with self.assertRaises(BudgetError):
            self.ledger.reserve("profile", ".01")

    def test_reservation_no_cached_discount(self):
        self.assertGreater(reservation_usd("hello", 3, 256), usage_usd({"input_tokens": 12288, "output_tokens": 256}))

    def test_client_missing_usage_blocks_and_does_not_log_key(self):
        class Response:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_lines(self, **kwargs): return iter([])
        class Session:
            def post(self, *args, **kwargs): return Response()
        client = ApiClient("secret-test-key", self.path, session=Session())
        png = b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + (640).to_bytes(4, "big") + (480).to_bytes(4, "big")
        with self.assertRaises(RuntimeError):
            client.decide("test", [png], legal_action)
        self.assertTrue(self.ledger.snapshot()["blocked"])
        self.assertNotIn("secret-test-key", Path(self.path).read_text())

    def test_known_incomplete_usage_is_settled(self):
        class Response:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_lines(self, **kwargs):
                yield b'data: {"type":"response.incomplete","response":{"model":"gpt-6.1-sol","service_tier":"ultrafast","usage":{"input_tokens":10,"output_tokens":128}}}'
        class Session:
            def post(self, *args, **kwargs): return Response()
        client = ApiClient("secret-test-key", self.path, session=Session())
        png = b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + (640).to_bytes(4, "big") + (480).to_bytes(4, "big")
        with self.assertRaises(RuntimeError):
            client.decide("test", [png], legal_action)
        state = self.ledger.snapshot()
        self.assertFalse(state["blocked"])
        self.assertEqual(next(iter(state["requests"].values()))["status"], "settled")

    def test_invalid_actions_rejected(self):
        for invalid in ("[0,1,1,0,999]", "[[9,1,1,0,6]]", "[0,true,1,0,6]"):
            with self.assertRaises(ValueError):
                legal_action(invalid)
        self.assertTrue(legal_action("[[0,1,1,0,6],[1,1,1,0,12]]"))


if __name__ == "__main__":
    unittest.main()
