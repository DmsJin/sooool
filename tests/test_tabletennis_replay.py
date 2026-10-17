"""Keep latest model intent distinct from the native stroke already installed."""
import unittest

from environments.tabletennis.replay import _execution_caption, _run_labels


class ReplayTests(unittest.TestCase):
    def test_labels_distinguish_subscription_simulation_from_actual_api(self):
        summary = {"source": "sol", "clock_mode": "subscription_with_simulated_api_profile",
                   "clock": {"requested_slowdown": 1}}
        self.assertEqual(_run_labels(summary),
                         ("SUBSCRIPTION / SIM", "Simulation wall time (game may pause)"))
        summary["clock_mode"] = "actual_wall_sol"
        self.assertEqual(_run_labels(summary), ("SUBSCRIPTION / 1x", "1x actual wall time"))
        summary["source"] = "api"
        self.assertEqual(_run_labels(summary), ("REAL API / 1x", "1x actual wall time"))
        summary["source"] = "rules"
        summary["clock"]["requested_slowdown"] = 3
        self.assertEqual(_run_labels(summary), ("RULE BASELINE / S3", "S3 actual wall time"))

    def test_caption_tracks_commitment_point_boundaries_and_completion(self):
        state = {"point": 2, "ball": "opponent's return", "t_since_played": .5}
        selection = {"policy": "wide_left", "intent_id": 4, "selected": True}
        leg = (2, "opponent's return", 150)
        caption = _execution_caption(state, 200, selection, leg, 5, False)
        self.assertIn("Executing: wide_left / reply #4", caption)
        self.assertIn("Reply #5 awaits next flight", caption)
        state["ball"] = "going away"
        self.assertEqual(_execution_caption(state, 200, selection, leg, 5, False),
                         "Last return: wide_left / reply #4.")
        state["point"] = 3
        self.assertEqual(_execution_caption(state, 200, selection, leg, 5, False),
                         "Intent accepted; awaiting next stroke.")
        state["ball"] = "your serve"
        self.assertEqual(_execution_caption(state, 200, selection, leg, 5, False),
                         "Executing: synchronized RULE service.")
        self.assertEqual(_execution_caption(state, 200, selection, leg, 5, True), "Match complete.")


if __name__ == "__main__":
    unittest.main()
