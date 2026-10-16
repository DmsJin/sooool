"""No-burst cadence, stale-plan rejection and paid API boundaries, without model calls."""
import json
from pathlib import Path
import tempfile
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from environments.tabletennis.execution import wait_tick, install_prepared
from runtime.api import ApiBudget, ApiClient


class RealtimeTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("TABLETENNIS_ENV_ROOT"), "Requires public flight constants")
    def test_countershot_contact_law_and_legal_landing(self):
        from environments.tabletennis.native import ROOT, load_plugin
        from environments.tabletennis.perception import countershot
        import sys
        reference=load_plugin(ROOT/"sports/tabletennis/plugin.py").players()["reference"]
        bp=sys.modules[reference.__module__]
        position,incoming=np.array([0.,-1.1,.3]),np.array([0.,-2.5,0.])
        valid,normal,paddle,outgoing=countershot(position,incoming,np.array([0.,.4]),bp.G,bp.KD)
        self.assertTrue(valid)
        self.assertLessEqual(np.linalg.norm(paddle),1.45+1e-8)
        np.testing.assert_allclose(outgoing,incoming+1.8*np.dot(paddle-incoming,normal)*normal)
        landing,clear=bp.landing(position,outgoing)
        self.assertTrue(clear)
        self.assertGreater(landing[1],0)
        self.assertLess(landing[1],1.37)

    @unittest.skipUnless(os.environ.get("TABLETENNIS_ENV_ROOT"), "Requires native robot servo")
    def test_rehearsal_keeps_live_reflex_time_base(self):
        from environments.tabletennis.native import ROOT, load_plugin
        from environments.tabletennis.execution import rehearse_robot
        load_plugin(ROOT / "sports/tabletennis/plugin.py")
        from duel import Planner
        player = Planner("A")
        player.s.d.time = 10.
        player.s.servo.reflex_at = (9., player.s.d.qpos[player.s._qadr].copy())
        rehearse_robot(player, [player.s._target.copy() for _ in range(3)], 3)
        self.assertAlmostEqual(player._twin.d.time, 10.03)
        self.assertIsNone(player._twin.servo.reflex_at)

    @unittest.skipUnless(os.environ.get("TABLETENNIS_ENV_ROOT"), "Requires the pinned public flight model")
    def test_return_solver_lands_across_nearby_camera_estimates(self):
        from environments.tabletennis.native import ROOT, load_plugin
        from environments.tabletennis.perception import rollout, solve_out
        from functools import partial
        import sys
        reference = load_plugin(ROOT / "sports/tabletennis/plugin.py").players()["reference"]
        bp = sys.modules[reference.__module__]
        flight = partial(rollout, gravity=bp.G, drag=bp.KD, radius=bp.BALL_R,
                         ez=bp.E_BOUNCE_Z, exy=bp.E_BOUNCE_XY, table_x=bp.TABLE_X, table_y=bp.TABLE_Y)
        for dx in (-.01, 0, .01):
            position = np.array([.56+dx, -.90, .24])
            velocity, clear = solve_out(position, [0, .8], 3.4, flight=flight,
                                        radius=bp.BALL_R, net_z=bp.NET_Z)
            self.assertTrue(clear)
            positions, _, bounces = flight(position, velocity, .001, 2000)
            self.assertTrue(bounces)
            np.testing.assert_allclose(positions[bounces[0], :2], [0, .8], atol=.02)

    @unittest.skipUnless(os.environ.get("TABLETENNIS_ENV_ROOT"), "Requires the pinned reference implementation")
    def test_batched_fit_matches_reference(self):
        from environments.tabletennis.native import ROOT, load_plugin
        from environments.tabletennis.perception import fit_flight
        import sys
        reference = load_plugin(ROOT / "sports/tabletennis/plugin.py").players()["reference"]
        native = sys.modules[reference.__module__]
        positions, _, _ = native.rollout([.1, .8, .4], [.2, -2, .9], .002, 120, bounce=False)
        observations = [(step * .002, positions[step]) for step in (0, 20, 40, 60, 80, 100)]
        for options in ({}, {"fit_accel": True}, {"a_fixed": np.array([.1, .2, 0])}):
            with self.subTest(options=options):
                original = native.fit_flight(observations, **options)
                batched = fit_flight(observations, gravity=native.G, drag=native.KD, **options)
                for a, b in zip(original, batched):
                    np.testing.assert_allclose(a, b, atol=1e-6, rtol=1e-6)

    @unittest.skipUnless(os.environ.get("TABLETENNIS_ENV_ROOT"), "Requires the pinned reference implementation")
    def test_compiled_rollout_matches_reference(self):
        from environments.tabletennis.native import ROOT, load_plugin
        from environments.tabletennis.perception import rollout
        import sys
        reference = load_plugin(ROOT / "sports/tabletennis/plugin.py").players()["reference"]
        native = sys.modules[reference.__module__]
        for bounce in (False, True):
            original = native.rollout([.1, -.8, .3], [.2, 3, -1], .002, 500, bounce=bounce)
            compiled = rollout([.1, -.8, .3], [.2, 3, -1], .002, 500, bounce=bounce,
                gravity=native.G, drag=native.KD, radius=native.BALL_R, ez=native.E_BOUNCE_Z,
                exy=native.E_BOUNCE_XY, table_x=native.TABLE_X, table_y=native.TABLE_Y)
            np.testing.assert_allclose(compiled[0], original[0], atol=1e-12, rtol=1e-12)
            np.testing.assert_allclose(compiled[1], original[1], atol=1e-12, rtol=1e-12)
            self.assertEqual(compiled[2], original[2])

    def test_clock_does_not_burst_after_a_stall(self):
        clock = [0.0]
        def sleep(seconds):
            clock[0] += seconds
        with patch("environments.tabletennis.execution.time.monotonic", side_effect=lambda: clock[0]), \
                patch("environments.tabletennis.execution.time.sleep", side_effect=sleep):
            first = wait_tick(0, .01)
            clock[0] += .3
            after_stall = wait_tick(first, .01)
            following = wait_tick(after_stall, .01)
        self.assertAlmostEqual(first, .01)
        self.assertAlmostEqual(after_stall, .31)
        self.assertAlmostEqual(following, .32)

    def test_late_or_changed_anchor_is_never_installed(self):
        core = SimpleNamespace(s=SimpleNamespace(_target=np.zeros(9)))
        env = SimpleNamespace(frame=100, state=lambda: {"point": 1}, match=SimpleNamespace(R=core))
        self.assertEqual(install_prepared(env, {"point": 2}, {}), {"discarded": "previous_point"})
        self.assertEqual(install_prepared(env, {"point": 1}, {"install_frame": 99}),
                         {"discarded": "missed_install_deadline"})
        self.assertEqual(install_prepared(env, {"point": 1}, {"install_frame": 100, "anchor": np.ones(9)}),
                         {"discarded": "command_anchor_changed"})

    def test_api_payload_keeps_exact_requested_model_effort_and_tier(self):
        client = ApiClient.__new__(ApiClient)
        client.instructions, client.max_output_tokens, client.schema = "public game", 1024, {"type": "object"}
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "camera.png"
            Image.new("RGB", (2, 2)).save(image)
            payload = client._payload("choose policy", [image])
        self.assertEqual(payload["model"], "gpt-6.1-sol")
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertEqual(payload["service_tier"], "ultrafast")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["tools"], [])

    def test_existing_budget_is_preserved_and_calls_settle_once(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "budget.jsonl"
            budget = ApiBudget(path, 20)
            reservation = budget.reserve(100, 100)
            cost = budget.settle(reservation, {"input_tokens": 100, "cached_tokens": 0,
                "cache_write_tokens": 0, "output_tokens": 10, "reasoning_tokens": 3})
            self.assertAlmostEqual(cost, .0018)
            self.assertEqual(budget.snapshot()["unresolved_requests"], 0)
            with self.assertRaises(ValueError):
                budget.settle(reservation, {"input_tokens": 0, "cached_tokens": 0,
                    "cache_write_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0})
            with self.assertRaises(ValueError):
                ApiBudget(path, 21)
            self.assertEqual(json.loads(path.read_text().splitlines()[0])["limit_nano_usd"], 20_000_000_000)


if __name__ == "__main__":
    unittest.main()
