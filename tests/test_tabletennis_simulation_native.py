"""Exercise native trajectory installation under virtual advancement, without a model."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class _SubscriptionStub:
    def __init__(self, **kwargs):
        pass

    def act(self, prompt, images, directory):
        return json.dumps({"policy": "wide_right", "memory": "",
                           "decision_summary": "Native installation regression test."}), {"wall_seconds": 0.}

    def close(self):
        pass


@unittest.skipUnless(os.environ.get("TABLETENNIS_ENV_ROOT"), "Requires pinned native table tennis and EGL")
class NativeSimulationTests(unittest.TestCase):
    def test_virtual_physics_installs_a_real_plan_with_no_model_client(self):
        from environments.tabletennis.runner import run_episode
        config = {
            "source": "sol", "simulation": True, "seed": 11, "level": 1,
            "duration": 4, "slowdown": 1, "capture_stride": 5, "observation_stride": 5,
            "model_workers": 4, "max_calls": 1, "request_interval_s": .65,
            "subscription_service_tier": "priority", "delay_seed": 7319,
            "clock": "subscription_with_simulated_api_profile",
            "latency_profile": {"delays_s": [.1], "all_wire_completed_request_s": [.15]},
        }
        with tempfile.TemporaryDirectory() as directory, \
             patch("environments.tabletennis.runner.SubscriptionClient", _SubscriptionStub):
            output = Path(directory) / "native-sim"
            result = run_episode(config, output)
            self.assertIsNone(result["error"])
            self.assertGreater(result["plans_installed"], 0)
            self.assertEqual(result["model_invalid"], 0)
            events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
            accepted = [event for event in events if event["event"] == "intent_accepted"]
            self.assertEqual(len(accepted), 1)
            self.assertGreaterEqual(accepted[0]["receipt_frame"], accepted[0]["delivery_frame"])


if __name__ == "__main__":
    unittest.main()
