"""Long-lived public-camera goal execution regressions owned by badminton."""
import base64
import io
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

from .tactics import TacticalPlayer

INTENT = {"normal": {"side": "left", "shot": "clear"},
          "under_pressure": {"side": "center", "shot": "clear"},
          "opponent_back": {"side": "right", "shot": "drop"},
          "recovery": [-.5, -2], "horizon_game_s": 5, "memory": ""}

@unittest.skipUnless(os.environ.get("BADMINTON_ENV_ROOT"), "Requires pinned native badminton")
class GoalExecutionTests(unittest.TestCase):
    """Long-lived camera regressions for SOL goals refused by the fixed-contact search."""

    def cases(self):
        return json.loads((Path(__file__).parent / "fixtures/goals.json").read_text())

    def play(self, spec, case, choice):
        from .native import load_sport
        bp = sys.modules[load_sport().players()["reference"].__module__]

        player = TacticalPlayer(spec, bp.Reference)
        state = case["state"]
        player.reset_point(state["point"])
        ref = player.reference
        ref.obs = [(at, np.asarray(position)) for at, position in case["observations"]]
        ref.flight = (state["point"], round(state["step"] / 100 - state["t_since_played"], 3))
        intent = {**INTENT, **{key: choice for key in ("normal", "under_pressure", "opponent_back")}}
        player.accept(intent, 7, source_game_time=state["step"] / 100)
        png = io.BytesIO()
        Image.new("RGB", (1920, 720)).save(png, format="PNG")
        action = player.act({"state": state, "observation": {
            "image_png_b64": base64.b64encode(png.getvalue()).decode(), "view_sim_times": []}})
        return player, action

    def test_previously_refused_drops_use_the_single_goal(self):
        fixture = self.cases()
        exact = 0
        for case in fixture["cases"]:
            with self.subTest(frame=case["state"]["step"]):
                player, action = self.play(fixture["spec"], case, case["choice"])
                self.assertEqual(action["type"], "act")
                self.assertIn(player.selection["goal_status"], {"exact", "projected"})
                exact += player.selection["goal_status"] == "exact"
                old_error = float(np.linalg.norm(np.asarray(case["old_target"]) - player.selection["requested_target"]))
                self.assertLess(player.selection["target_error_m"], old_error)
                self.assertGreaterEqual(player.selection["net_clearance_m"], .10)
                self.assertNotEqual(player.selection["predicted_landing"], case["old_target"])
        self.assertGreaterEqual(exact, 2)

    def test_same_incoming_ball_changes_placement_when_sol_changes_the_goal(self):
        fixture = self.cases()
        case = fixture["cases"][0]
        landings = {}
        for side, shot in (("left", "clear"), ("right", "clear"), ("left", "drop"), ("right", "drop")):
            player, action = self.play(fixture["spec"], case, {"side": side, "shot": shot})
            self.assertEqual(action["type"], "act")
            landings[side, shot] = player.selection["predicted_landing"]
        for shot in ("clear", "drop"):
            self.assertLess(landings["left", shot][0], -.3)
            self.assertGreater(landings["right", shot][0], .3)
        for side in ("left", "right"):
            self.assertGreater(landings[side, "clear"][1] - landings[side, "drop"][1], .6)

    def test_pending_candidate_waits_for_installation_and_keeps_original_goal(self):
        """A later SOL reply cannot overwrite a pending or installed stroke's goal."""
        fixture = self.cases()
        case = fixture["cases"][0]
        player, _ = self.play(fixture["spec"], case, case["choice"])
        proposed = player.candidates[0]
        self.assertIsNone(player.reference.plan)
        opposite = {"side": "left" if case["choice"]["side"] == "right" else "right", "shot": "clear"}
        player.accept({**INTENT, **{key: opposite for key in ("normal", "under_pressure", "opponent_back")}},
                      8, source_game_time=case["state"]["step"] / 100)
        png = io.BytesIO()
        Image.new("RGB", (1920, 720)).save(png, format="PNG")
        action = player.act({"state": case["state"], "observation": {
            "image_png_b64": base64.b64encode(png.getvalue()).decode(), "view_sim_times": []}})
        self.assertIsNone(action)
        self.assertEqual(player.feedback["reason"], "awaiting_rehearsal")
        player.acknowledge({"point": case["state"]["point"], "source_frame": case["state"]["step"],
                            "status": "installed", "plan": proposed})
        self.assertEqual(player.reference.plan["goal_choice"], case["choice"])
        self.assertEqual(player.reference.plan["selection"]["intent_id"], 7)

    def test_rejected_rehearsal_moves_every_candidate_to_a_later_contact(self):
        """Long-lived regression: alternative stances must respect a rejected contact."""
        fixture = self.cases()
        case = fixture["cases"][0]
        player, _ = self.play(fixture["spec"], case, case["choice"])
        rejected_contact = min(plan["t"] for plan in player.candidates)
        player.acknowledge({"point": case["state"]["point"], "source_frame": case["state"]["step"],
                            "status": "rejected", "earliest_contact": rejected_contact})
        png = io.BytesIO()
        Image.new("RGB", (1920, 720)).save(png, format="PNG")
        action = player.act({"state": case["state"], "observation": {
            "image_png_b64": base64.b64encode(png.getvalue()).decode(), "view_sim_times": []}})
        self.assertIsNotNone(action)
        self.assertTrue(player.candidates)
        for candidate in player.candidates:
            self.assertGreaterEqual(candidate["t"], rejected_contact + .10)

    def test_rehearsed_velocity_controls_admission_even_when_stroke_reports_ok(self):
        """Retain the real low-return failure and a legal middle-contact rehearsal."""
        from .realtime import assess_delivery
        from .tactics import _goal
        fixture = json.loads((Path(__file__).parent / "fixtures/low-reception.json").read_text())
        case = fixture["case"]
        player, _ = self.play(fixture["spec"], case, case["choice"])
        bp = player.bp
        at, position, velocity, _ = bp.fit(player.reference.obs)
        times, _, incoming = bp.predict(position, velocity, at)
        for delivery in case["deliveries"]:
            with self.subTest(contact=delivery["contact_game_time"]):
                index = int(np.argmin(abs(times - delivery["contact_game_time"])))
                plan = {**delivery["command"], "incoming": incoming[index],
                        "goal_choice": case["choice"], "target": _goal(bp, case["choice"]),
                        "goal_status": "projected" if delivery["valid"] else "rule_fallback"}
                result = assess_delivery(plan, delivery["feedback"])
                self.assertEqual(result["valid"], delivery["valid"], result)
                if not delivery["valid"]:
                    self.assertEqual(delivery["feedback"]["stroke"], "ok")
                    self.assertIn("outgoing_flight", result["reasons"])
                    self.assertEqual(result["goal_status"], "rule_fallback")
