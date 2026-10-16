"""Long-lived API, clock and video contracts owned by the badminton realtime runner."""
import json
import os
from pathlib import Path
import struct
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from .api import TacticalAPI, decode_response
from . import realtime
from .realtime import _control, run_realtime
from .realtime_report import audit_realtime, decision_panel

ROOT = Path(__file__).resolve().parents[2]
PACKET = {**{branch: {"side": "left", "shot": "clear"} for branch in ("normal", "under_pressure", "opponent_back")},
          "recovery": [0, -1.6], "horizon_game_s": 10, "memory": "",
          "brief": "Play a deep left clear and recover centrally."}
SPEC = {"base": {"range": {"x": [-1.5, 1.5], "y": [-3.53, -.5]}}}


class Stream:
    """Supply complete public JSON before the terminal usage event."""

    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_lines(self, chunk_size):
        for event in self.events:
            yield b"data: " + json.dumps(event).encode()


class RealtimeBoundaryTests(unittest.TestCase):
    def test_goal_contact_keeps_absolute_time_and_native_serve_keeps_its_lead(self):
        """Prevent the realtime adapter from adding lead twice to a goal contact."""
        for selection, contact in (({"kind": "rally"}, 2.2), (None, 2.34)):
            with self.subTest(selection=selection), tempfile.TemporaryDirectory() as temp:
                Path(temp, "images").mkdir()
                player = SimpleNamespace(point=1, reference=SimpleNamespace(lead=14), selection=selection,
                    intent=None, intent_id=None, feedback=None,
                    act=lambda view: {"type": "act", "t": 1.2})
                sport = SimpleNamespace(worker_call=lambda *args: {"png": b"camera"})
                with patch.object(realtime, "_player", player), \
                        patch.object(realtime, "_sport", sport), \
                        patch.object(_control, "spec", SPEC, create=True), \
                        patch.object(_control, "slowdown", 3, create=True):
                    row = _control({}, {"step": 100, "point": 1}, {}, None, None, None,
                                   "", [], {"summary": {}}, temp, 0.)
                self.assertEqual(row["command"]["contact_at_game_time"], contact)

    def test_summary_and_tactics_are_validated_together(self):
        self.assertEqual(decode_response(json.dumps(PACKET), SPEC)["brief"], PACKET["brief"])
        for change in ({"brief": ""}, {"brief": "x" * 61}, {"normal": {"side": "up", "shot": "clear"}}, {"recovery": [True, -1]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                decode_response(json.dumps({**PACKET, **change}), SPEC)

    def test_early_complete_answer_is_published_before_terminal_billing_and_mismatch_blocks(self):
        recipe = json.loads((ROOT / "recipes/badminton-realtime.json").read_text())
        answer = json.dumps(PACKET)
        image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 1920, 720)
        for consistent in (True, False):
            with self.subTest(consistent=consistent), tempfile.TemporaryDirectory() as temp:
                client = TacticalAPI("test-only", temp, 20, recipe)
                terminal = {"id": "response", "status": "completed", "model": recipe["model"],
                            "service_tier": "ultrafast", "usage": {"input_tokens": 100, "output_tokens": 25},
                            "output": [{"content": [{"type": "output_text", "text": answer if consistent else "{}"}]}]}
                events = [{"type": "response.created", "response": {"model": recipe["model"], "service_tier": "ultrafast"}},
                          {"type": "response.output_text.delta", "delta": answer},
                          {"type": "response.completed", "response": terminal}]
                published = []
                def accept(packet):
                    self.assertEqual(next(iter(client.ledger.snapshot()["requests"].values()))["status"], "inflight")
                    published.append(packet)
                with patch.object(client.session, "post", return_value=Stream(events)) as post:
                    if consistent:
                        result = client.act("public task", image, SPEC, Path(temp) / "request", accept)
                        self.assertGreater(float(result["cost_usd"]), 0)
                    else:
                        with self.assertRaisesRegex(RuntimeError, "terminal answer differs"):
                            client.act("public task", image, SPEC, Path(temp) / "request", accept)
                    payload = post.call_args.kwargs["json"]
                    self.assertEqual(payload["service_tier"], "ultrafast")
                    self.assertNotIn("tools", payload)
                self.assertEqual(len(published), 1)
                self.assertEqual(next(iter(client.ledger.snapshot()["requests"].values()))["status"], "settled")
                self.assertEqual(client.ledger.snapshot()["blocked"] is None, consistent)
                client.close()

    def test_panel_waits_for_acceptance_and_clears_intent_at_point_boundary(self):
        initial = {"brief": "Waiting", "intent": None}
        history = []
        self.assertEqual(decision_panel([{"event": "request_issued"}], initial, history), initial)
        accepted = {"event": "intent_accepted", "brief": PACKET["brief"], "intent": {k: v for k, v in PACKET.items() if k != "brief"},
                    "id": 0, "capture_to_accept_seconds": 2}
        current = decision_panel([accepted], initial, history)
        self.assertEqual(current["brief"], PACKET["brief"])
        current = decision_panel([{"event": "soft_reset"}], current, history)
        self.assertIsNone(current["intent"])
        self.assertNotEqual(current["brief"], PACKET["brief"])

    def test_terminal_failure_retains_provider_error_and_unknown_cost_reservation(self):
        """A real missing-usage failure must retain evidence for billing reconciliation."""
        recipe = json.loads((ROOT / "recipes/badminton-realtime.json").read_text())
        image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 1920, 720)
        response = {"id": "failed-response", "status": "failed", "usage": None,
                    "error": {"code": "credit_balance_exhausted", "message": "You have no credits remaining."}}
        events = [{"type": "response.failed", "response": response}]
        with tempfile.TemporaryDirectory() as temp:
            client = TacticalAPI("test-only", temp, 20, recipe)
            directory = Path(temp) / "request"
            with patch.object(client.session, "post", return_value=Stream(events)), \
                    self.assertRaisesRegex(RuntimeError, "credit_balance_exhausted"):
                client.act("public task", image, SPEC, directory, self.fail)
            self.assertEqual(json.loads((directory / "response.json").read_text()), response)
            self.assertEqual(json.loads((directory / "events.jsonl").read_text())["response"], response)
            ledger = client.ledger.snapshot()
            self.assertIsNotNone(ledger["blocked"])
            self.assertEqual(next(iter(ledger["requests"].values()))["status"], "unknown")
            client.close()


@unittest.skipUnless(os.environ.get("BADMINTON_ENV_ROOT"), "Requires the pinned GPU/native runtime")
class NativeClockTests(unittest.TestCase):
    def test_audit_checks_observations_after_same_frame_command_application(self):
        """A live capture at the effect step includes the command that just took effect."""
        from .native import Action, BadmintonEnvironment
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            env = BadmintonEnvironment(level=1, seed=101, max_env_steps=2, slowdown=3)
            try:
                env.reset(render=False)
                before = env.public_state()
                env._layer.lead = 0
                command = {"type": "act", "t": 1.3, "pos": [.6476, -1.0724, 1.05],
                           "normal": [-.2196, .4492, .866], "vel": [-.3116, .6374, 1.2288]}
                job = env._layer.snapshot("A", command, env.match, 0)
                low, planning = env._layer.lower("A", command, env._layer.prepare(job), env.match)
                applied = env.match.apply("A", low)
                after = env.public_state()
                self.assertNotEqual(before["command"], after["command"])
                env.step(Action(None, "noop", True))
                events = [{"event": "executed", "frame": 0, "action": low, "selection": None,
                           "action_result": {**planning, **applied}},
                          {"event": "observation", "frame": 0, "state": after}]
                (directory / "run.json").write_text(json.dumps({"seed": 101, "window_steps": 1,
                    "config": {"level": 1, "slowdown": 3}}))
                (directory / "summary.json").write_text(json.dumps({"frames": 1, "points_for": 0,
                    "points_against": 0, "native_match_completed": False}))
                (directory / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
                self.assertTrue(audit_realtime(directory)["matched"])
            finally:
                env.close()

    def test_actual_physics_advances_while_api_request_is_pending(self):
        """The real control loop must not wait for the delayed API worker."""
        recipe = json.loads((ROOT / "recipes/badminton-realtime.json").read_text())
        config = {**recipe["args"], "max_game_seconds": 8, "observation_stride": 1}
        prompts = []
        class DelayedAPI:
            def __init__(self, *args):
                self.ledger = self
                self.calls = 0
            def act(self, prompt, image, spec, directory, publish):
                prompts.append(prompt)
                self.calls += 1
                started = time.monotonic()
                time.sleep(1)
                publish({"intent": {k: v for k, v in PACKET.items() if k != "brief"}, "brief": Path(directory).name,
                         "json_ready_monotonic": time.monotonic()})
                return {"timing": {"json_ready_seconds": time.monotonic() - started, "terminal_seconds": time.monotonic() - started}}
            def snapshot(self):
                return {"blocked": None, "requests": {}, "committed_usd": "0"}
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as temp:
            config["stop_file"] = str(Path(temp) / "STOP")
            profile = json.loads((ROOT / recipe["profile"]).read_text())
            with patch.object(realtime, "TacticalAPI", DelayedAPI):
                summary = run_realtime(config, recipe, profile, Path(temp) / "run", key="fake", budget_usd=20)
            events = [json.loads(line) for line in (Path(temp) / "run/events.jsonl").read_text().splitlines()]
            issued = next(e for e in events if e["event"] == "request_issued")
            accepted = next(e for e in events if e["event"] == "intent_accepted")
            for event in events:
                if event["event"] == "intent_accepted":
                    self.assertEqual(event["brief"], f'request-{event["id"]:05d}')
            delivered = {e["source_frame"] for e in events if e["event"] in {
                "executed", "command_rejected", "command_discarded", "planning_discarded"}}
            for event in events:
                if (event["event"] == "feedback_check" and event["source_frame"] < summary["frames"] - 100
                        and event["feedback"] is not None and (event["feedback"]["reason"] == "stroke_selected"
                                                               or event["feedback"]["repaired"])):
                    self.assertIn(event["source_frame"], delivered, "A selected stroke was silently lost behind another command")
            self.assertGreaterEqual(accepted["frame"] - issued["frame"], int(90 / config["slowdown"]))
            self.assertTrue(all(f'"slowdown":{config["slowdown"]}' in prompt for prompt in prompts))
            self.assertAlmostEqual(summary["wall_seconds"], summary["game_seconds"] * config["slowdown"], delta=.1)
            self.assertTrue(summary["clock_valid"])


if __name__ == "__main__":
    unittest.main()
