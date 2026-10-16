"""Tactical boundary and per-flight commitment checks; no native game or model needed."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np

from environments.tabletennis.tactics import TacticalPlayer, decode_intent, format_prompt


class TacticalTests(unittest.TestCase):
    def test_service_toss_and_contact_share_one_absolute_schedule(self):
        player = TacticalPlayer.__new__(TacticalPlayer)
        base = np.array([.2, -1.87])
        recipe = dict(base=base, t_from_projection=.525, v_out=np.array([0, 3, -1]))
        player.reference = SimpleNamespace(srv=None, base_rest=base, home=np.zeros(2),
                                           _settled=lambda *args: True)
        player.service_plan = ({"pos": [0,-1.42,.27], "height": .28},recipe)
        player.bp = SimpleNamespace(TOSS_REST=10, serve_plan=lambda *args, **kwargs:
            ({"pos": [0, -1.42, .27], "height": .28}, recipe),
            toss_speed=lambda h: 2.4,
            toss_flight=lambda *args: (np.zeros(3), np.ones(3)),
            paddle_for=lambda *args: (np.zeros(3), np.ones(3), np.ones(3)))
        state = {"point": 1, "step": 100, "serve": {"phase": "open"}}
        action = player.serve(state)
        schedule = player.serve_request
        self.assertEqual(schedule["toss_frame"], 175)
        self.assertEqual(schedule["contact_frame"], 175+10+52)
        self.assertEqual(action["t"]*100, schedule["contact_frame"]-100)
        self.assertIsNone(player.serve(state))

    def test_committed_stroke_waits_for_post_bounce_evidence(self):
        player = TacticalPlayer.__new__(TacticalPlayer)
        leg = {"acts": [{"phase": "pre"}], "heard": [], "frames": {}, "launch": 0}
        player.reference = SimpleNamespace(P=SimpleNamespace(leg=leg, predict=lambda: (1.,)))
        player.rule_decide = Mock(return_value="correction")
        self.assertIsNone(player.decide(lambda: 0))
        player.rule_decide.assert_not_called()
        leg.update(heard=[{"event": "bounce on your half", "t": .2}],
                   frames={.22: None, .24: None, .26: None})
        self.assertEqual(player.decide(lambda: 0), "correction")
        leg["acts"][-1]["phase"] = "post"
        self.assertIsNone(player.decide(lambda: 0))
        self.assertEqual(player.rule_decide.call_count, 1)

    def test_intent_contract_and_private_input_filter(self):
        self.assertEqual(decode_intent('{"policy":"wide_left","memory":"","decision_summary":"Opponent on right; target left."}')["policy"], "wide_left")
        for value in ({"policy": "unknown", "memory": ""}, {"policy": [], "memory": ""},
                      {"policy": "reference", "memory": "x" * 1201}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode_intent(json.dumps(value))
        with self.assertRaises(ValueError):
            decode_intent('{"policy":"reference","policy":"wide_left","memory":""}')
        self.assertNotIn("PRIVATE", format_prompt({"seed": "PRIVATE", "truth": "PRIVATE", "score": [0, 0]}))

    def test_context_uses_public_camera_estimate_and_reports_its_age(self):
        player = TacticalPlayer.__new__(TacticalPlayer)
        leg = {"kind": "return", "launch": 100, "frames": {.04: np.array([.3, 1.2, .4])}}
        player.reference = SimpleNamespace(P=SimpleNamespace(leg=leg))
        player.flight_intent, player.intent = ("safe_center", 1), ("wide_left", 2)
        context = player.context({"step": 140, "ball_state": "coming to you"})
        self.assertEqual(context["opponent_last_seen_at_strike"], {"x": .3, "age_game_seconds": .36})
        self.assertEqual(context["current_flight_policy"], "safe_center")
        self.assertEqual(context["next_flight_policy"], "wide_left")

    def test_policy_changes_only_on_new_flight_and_falls_back_when_infeasible(self):
        player = TacticalPlayer.__new__(TacticalPlayer)
        reference = SimpleNamespace(leg={"key": (1, "serve", 0)}, vp_max=2, tangential=True)
        player.reference = SimpleNamespace(P=reference)
        player.intent, player.locked_leg = ("wide_left", 1), None
        player.rule_stroke = lambda *args: "rule"
        player.bp = SimpleNamespace(
            G=np.array([0.,0.,-9.81]), KD=.13, OFFSET=.0275,
            solve_out=lambda position, aim, speed: (np.array([0, speed, 1]), True),
            paddle_for=lambda *args: (np.zeros(3), np.array([0, 1, 0]), np.array([0, 1, 0])))
        self.assertLess(player.stroke(np.zeros(3), np.zeros(3))[3][0], 0)
        player.accept({"policy": "wide_right"}, 2)
        self.assertLess(player.stroke(np.zeros(3), np.zeros(3))[3][0], 0)
        reference.leg = {"key": (1, "return", 100)}
        self.assertGreater(player.stroke(np.zeros(3), np.zeros(3))[3][0], 0)
        reference.vp_max = .1
        self.assertGreater(player.stroke(np.zeros(3), np.zeros(3))[3][0], 0)
        self.assertTrue(player.selection["selected"])
        player.bp.solve_out = lambda *args: (np.zeros(3), False)
        self.assertEqual(player.stroke(np.zeros(3), np.zeros(3)), "rule")
        self.assertEqual(player.selection["fallback"], "no_screened_candidate")


if __name__ == "__main__":
    unittest.main()
