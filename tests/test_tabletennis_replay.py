"""Keep latest model intent distinct from the native stroke already installed."""
import unittest

from environments.tabletennis.replay import _execution_caption


class ReplayTests(unittest.TestCase):
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
