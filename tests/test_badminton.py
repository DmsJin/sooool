"""Long-lived tactical input and subscription-tier contracts owned by badminton."""

import json
from collections import deque
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from environments.badminton.tactics import decode_intent, format_prompt
from environments.badminton.runner import run_episode
from runtime.subscription import SubscriptionClient


SPEC = {"base": {"range": {"x": [-1.5, 1.5], "y": [-3.53, -.5]}}, "seed": "PRIVATE_SEED"}
INTENT = {"normal": {"side": "left", "shot": "clear"},
          "under_pressure": {"side": "center", "shot": "clear"},
          "opponent_back": {"side": "right", "shot": "drop"},
          "recovery": [-.5, -2], "horizon_game_s": 5, "memory": "observed opponent back"}


class TacticalBoundaryTests(unittest.TestCase):
    def test_conditional_strategy_boundary_and_public_prompt(self):
        self.assertEqual(decode_intent(json.dumps(INTENT), SPEC), INTENT)
        for change in ({"normal": {"side": "up", "shot": "clear"}},
                       {"under_pressure": {"side": "left", "shot": "auto"}},
                       {"opponent_back": {}}, {"recovery": [True, -1]}, {"recovery": [2, -1]},
                       {"horizon_game_s": True}, {"horizon_game_s": float("nan")},
                       {"horizon_game_s": 0}, {"horizon_game_s": 11}, {"memory": "x" * 1201}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                decode_intent(json.dumps({**INTENT, **change}), SPEC)
        with self.assertRaises(ValueError):
            decode_intent('{"normal":{},"normal":{}}', SPEC)
        prompt = format_prompt({"spec": SPEC, "images": [{"path": "PRIVATE_PATH"}],
                                "state": {"truth": "PRIVATE_TRUTH", "score": {"you": 1},
                                          "control_ack": {"plan": "PRIVATE_REHEARSAL"}}})
        for secret in ("PRIVATE_SEED", "PRIVATE_PATH", "PRIVATE_TRUTH", "PRIVATE_REHEARSAL", "control_ack"):
            self.assertNotIn(secret, prompt)

class TacticalLoopTests(unittest.TestCase):
    def test_default_thread_accepts_null_echo_and_blocks_priority_or_extra_instructions(self):
        """Codex 0.162.1 echoes null for default; reject accelerated or contaminated turns."""
        with tempfile.TemporaryDirectory() as temp:
            for number, (tier, sources, allowed) in enumerate((
                    (None, [], True), ("default", [], True),
                    ("priority", [], False), (None, ["unexpected"], False))):
                with self.subTest(tier=tier, sources=sources):
                    client = SubscriptionClient.__new__(SubscriptionClient)
                    client.output = client.workspace = Path(temp)
                    client.service_tier, client.schema, client.counter, client.timeout = "default", None, 0, 1
                    client.pending = deque([
                        {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": "{}"}}},
                        {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
                    ])
                    reply = {"model": "gpt-6.1-sol", "reasoningEffort": "low", "serviceTier": tier,
                             "instructionSources": sources, "thread": {"id": "thread"}}
                    def rpc(method, params):
                        return reply if method == "thread/start" else {"turn": {"id": "turn"}}
                    with patch.object(client, "_rpc", side_effect=rpc) as calls, \
                            patch.object(client, "quota", return_value={}):
                        if allowed:
                            text, _ = client.act("game only", [], Path(temp) / str(number))
                            self.assertEqual(text, "{}")
                        else:
                            with self.assertRaisesRegex(RuntimeError, "Unexpected native tier"):
                                client.act("game only", [], Path(temp) / str(number))
                            self.assertFalse(any(call.args[0] == "turn/start" for call in calls.call_args_list))

    def test_default_subscription_disables_fast_and_rejects_wrong_echo(self):
        """The transport boundary must enforce the explicitly selected simulation tier."""
        with tempfile.TemporaryDirectory() as temp:
            for fast in (False, True):
                with self.subTest(fast=fast), patch("runtime.subscription.shutil.which", return_value="codex"), \
                        patch("runtime.subscription.subprocess.Popen") as process, \
                        patch.object(SubscriptionClient, "_rpc") as rpc:
                    process.return_value.stdout = []
                    rpc.side_effect = [{}, {"account": {"type": "chatgpt"}},
                                       {"config": {"service_tier": "default", "features": {"fast_mode": fast}}}]
                    if fast:
                        with self.assertRaisesRegex(RuntimeError, "did not disable Fast"):
                            SubscriptionClient(output=Path(temp), system="game only", service_tier="default")
                    else:
                        client = SubscriptionClient(output=Path(temp), system="game only", service_tier="default")
                        try:
                            command = process.call_args.args[0]
                            self.assertIn("features.fast_mode=false", command)
                            self.assertIn('service_tier="default"', command)
                        finally:
                            client.close()

    def test_subscription_latency_cannot_be_used_for_simulation(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(ValueError, "API Ultrafast"):
            run_episode({"slowdown": 3, "level": 1}, "sol", 101, Path(temp) / "episode", 1000,
                        {"source": "subscription"})

if __name__ == "__main__":
    unittest.main()
