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

    def test_delivery_correction_keeps_the_committed_goal_after_a_new_sol_reply(self):
        fixture = self.cases()
        case = fixture["cases"][0]
        player, _ = self.play(fixture["spec"], case, case["choice"])
        original_target = player.reference.plan["target"].copy()
        original_choice = dict(player.reference.plan["goal_choice"])
        state = dict(case["state"])
        state["command"] = {"phase": "approach", "contact_in_s": player.reference.plan["t"] - state["step"] / 100,
                            "pos_error_rehearsed_m": .08, "stroke": "pose not delivered",
                            "vel_rehearsed": player.reference.plan["vel"].tolist()}
        opposite = {"side": "left" if original_choice["side"] == "right" else "right", "shot": "clear"}
        player.accept({**INTENT, **{key: opposite for key in ("normal", "under_pressure", "opponent_back")}},
                      8, source_game_time=state["step"] / 100)
        png = io.BytesIO()
        Image.new("RGB", (1920, 720)).save(png, format="PNG")
        action = player.act({"state": state, "observation": {
            "image_png_b64": base64.b64encode(png.getvalue()).decode(), "view_sim_times": []}})
        self.assertIsNotNone(action, player.feedback)
        self.assertEqual(player.reference.plan["goal_choice"], original_choice)
        np.testing.assert_allclose(player.reference.plan["target"], original_target)
        self.assertEqual(player.selection["intent_id"], 7)
