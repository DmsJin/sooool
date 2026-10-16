"""Long-lived tactical authority and delayed fast-loop contracts owned by this experiment."""

import base64
from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from environments.badminton.tactics import decode_intent, format_prompt
from environments.badminton.runner import PROFILE_CALLS, run_episode
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
                                "state": {"truth": "PRIVATE_TRUTH", "score": {"you": 1}}})
        for secret in ("PRIVATE_SEED", "PRIVATE_PATH", "PRIVATE_TRUTH"):
            self.assertNotIn(secret, prompt)

@dataclass
class Action:
    value: object
    name: str
    is_noop: bool = False


class Env:
    def __init__(self):
        self.frame = 0
        self.actions = []
        self.sport = SimpleNamespace(players=lambda: {"reference": object})

    def reset(self, seed):
        return self.observe()

    def observe(self):
        return SimpleNamespace(env_step=self.frame, metadata={"spec": SPEC}, data={
            "state": {"point": 1 if self.frame < 15 else 2, "step": self.frame,
                      "ball_state": "coming to you", "ball_in_play": True, "you_serve": False,
                      "serve": {"phase": "done"}},
            "observation": {"image_png_b64": base64.b64encode(b"camera").decode()}})

    def step(self, action):
        self.actions.append((self.frame, action.value))
        self.frame += 1
        return SimpleNamespace(done=False, truncated=False, reward=0, info={
            "soft_reset": self.frame == 15,
            "task_metrics": {"points_for": 0, "points_against": 0, "success": False}})

    def close(self):
        pass


class FastPlayer:
    """Submit observable fast-loop actions while a model response is delayed."""

    def __init__(self, spec, reference):
        self.intent = self.intent_id = self.selection = self.feedback = None

    def reset_point(self, point):
        self.intent = self.intent_id = None

    def accept(self, intent, request_id, *, source_game_time):
        self.intent, self.intent_id = intent, request_id

    def act(self, view):
        return {"type": "act", "t": 2, "pos": [0, -1, 1], "normal": [0, 1, 0], "vel": [0, 1, 0]}


class Client:
    def act(self, prompt, images, directory):
        return json.dumps(INTENT), {"wall_seconds": .01, "token_usage": None}

    def close(self):
        pass


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

    def test_fast_actions_continue_during_model_delay_and_cross_point_reply_is_discarded(self):
        with tempfile.TemporaryDirectory() as temp:
            env = Env()
            output = Path(temp) / "episode"
            config = {"slowdown": 2, "level": 1, "stop_file": str(Path(temp) / "STOP")}
            profile = {"action_mode": "conditional_tactical_v1", "source": "api", "service_tier": "ultrafast",
                       "usable_for_simulation": True,
                       "samples": [{"latency_ms": 400, "service_ms": 400}] * PROFILE_CALLS}
            with patch("environments.badminton.runner._environment", return_value=(env, Action)), \
                    patch("environments.badminton.runner.TacticalPlayer", FastPlayer), \
                    patch("environments.badminton.runner._client", return_value=Client()):
                result = run_episode(config, "sol", 101, output, 40, profile)
            events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
            first_request = next(e for e in events if e["event"] == "request_issued")
            self.assertTrue(any(value is not None and first_request["frame"] <= frame < first_request["ready_frame"]
                                for frame, value in env.actions))
            self.assertTrue(any(e["event"] == "discarded" and e["reason"] == "previous_point" for e in events))
            self.assertEqual(result["accepted"], 0)
            for execution in (e for e in events if e["event"] == "executed"):
                self.assertEqual(execution["frame"] + round(execution["action"]["t"] * 100),
                                 execution["source_frame"] + 200)
            self.assertEqual(result["status"], "screen_completed")

    def test_subscription_latency_cannot_be_used_for_simulation(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(ValueError, "API Ultrafast"):
            run_episode({"slowdown": 2, "level": 1}, "sol", 101, Path(temp) / "episode", 40,
                        {"action_mode": "conditional_tactical_v1", "source": "subscription", "samples": [{}] * 100})

    def test_profile_ablation_keeps_delays_and_frozen_mode_stops_point_updates(self):
        """Ablations change model information or update authority, never injected delays."""
        profile = {"action_mode": "conditional_tactical_v1", "source": "api", "service_tier": "ultrafast",
                   "usable_for_simulation": True, "summary": {"mean": 100, "unit": "ms"},
                   "samples": [{"latency_ms": 100, "service_ms": 100}] * PROFILE_CALLS}
        with tempfile.TemporaryDirectory() as temp:
            counts = {}
            for source in ("sol", "sol-frozen"):
                output = Path(temp) / source
                config = {"slowdown": 2, "level": 1, "stop_file": str(Path(temp) / "STOP")}
                with patch("environments.badminton.runner._environment", return_value=(Env(), Action)), \
                        patch("environments.badminton.runner.TacticalPlayer", FastPlayer), \
                        patch("environments.badminton.runner._client", return_value=Client()):
                    result = run_episode(config, source, 101, output, 240, profile, profile_info=False)
                counts[source] = result["calls"]
                events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
                for request in (e for e in events if e["event"] == "request_issued"):
                    self.assertEqual(request["ready_frame"] - request["frame"], 5)
                for prompt in (output / "requests").glob("*/prompt.txt"):
                    self.assertNotIn("profile_summary", prompt.read_text())
            self.assertEqual(counts, {"sol": 3, "sol-frozen": 2})



if __name__ == "__main__":
    unittest.main()
