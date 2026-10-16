"""Camera-only reference execution with persistent online tactical preferences.

The reference owns serving, flight tracking, mechanical feedback and corrections.
Tactical preferences can replace a newly selected rally stroke, never a stroke
already in flight. Both experimental arms use this same player.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from . import public as badminton
from .public import _unique_object


POLICY_ROOT = Path(__file__).resolve().parents[2] / "policies/badminton/tactical-v1"
SCHEMA = json.loads((POLICY_ROOT / "schema.json").read_text())
PROMPT = (POLICY_ROOT / "prompt.txt").read_text()


def decode_intent(text, spec):
    """Validate the model boundary without repairing a tactical preference."""
    value = json.loads(text, object_pairs_hook=_unique_object)
    if not isinstance(value, dict) or set(value) != set(SCHEMA["required"]):
        raise ValueError("Tactical response requires side, shot, recovery and memory")
    for key in ("side", "shot"):
        if value[key] not in SCHEMA["properties"][key]["enum"]:
            raise ValueError(f"Invalid tactical {key}")
    recovery = value["recovery"]
    if not isinstance(recovery, list) or len(recovery) != 2:
        raise ValueError("Recovery requires two coordinates")
    for axis, coordinate in zip(("x", "y"), recovery):
        lo, hi = spec["base"]["range"][axis]
        if type(coordinate) not in (int, float) or not math.isfinite(coordinate) or not lo <= coordinate <= hi:
            raise ValueError(f"Recovery {axis} outside the public base range")
    if not isinstance(value["memory"], str) or len(value["memory"]) > 1200:
        raise ValueError("Memory must be a string of at most 1200 characters")
    return value


def format_prompt(snapshot):
    """Combine the frozen tactical task with its permitted public snapshot."""
    public = badminton.public_data({key: value for key, value in snapshot.items() if key != "images"})
    return PROMPT + json.dumps(public, separators=(",", ":"), allow_nan=False)


def _preferred(bp, ref, state, intent):
    """Screen one tactical shot using the reference's flight and reach models."""
    tf, position, velocity, _ = bp.fit(ref.obs)
    ts, positions, velocities = bp.predict(position, velocity, tf)
    now = state["step"] * bp.STEP + (ref.lead + 2) * bp.STEP
    x = {"left": -1, "center": 0, "right": 1}[intent["side"]] * .75 * bp.COURT_X
    depth, angles = {
        "clear": (.85 * bp.COURT_Y, bp.DEEP_THETAS),
        "drop": (.75 * bp.SHORT_Y, bp.SHORT_THETAS),
        "smash": (.5 * bp.COURT_Y, bp.SMASH_THETAS),
    }[intent["shot"]]
    target = np.array([x, depth])
    base = np.asarray(state["robot_base_xy"])
    candidates = []
    for i in range(0, len(ts), 5):
        p, dt = positions[i], ts[i] - now
        if dt < .22 or (ref.t_min is not None and ts[i] < ref.t_min):
            continue
        lo, hi = (bp.KILL_Z, bp.Z_KILL) if intent["shot"] == "smash" else (bp.Z_MIN, bp.Z_MAX)
        if not (lo <= p[2] <= hi and -(bp.COURT_Y + .7) <= p[1] < -.35 and abs(p[0]) <= bp.COURT_X + .9):
            continue
        if bp.base_time(float(np.linalg.norm(bp.stance(p) - base)), ref.vmax, ref.amax) <= dt - .12:
            candidates.append(i)
    pick = candidates[::max(1, len(candidates) // 12)]
    if intent["shot"] == "smash":
        pick = candidates
    best = None
    for i in pick:
        dt = ts[i] - now
        cap = bp.head_cap(dt)
        opts = bp.strokes(positions[i], velocities[i], target, angles, cap)
        if not opts:
            continue
        comfortable = 0 if bp.COMFORT_Z[0][0] <= positions[i][2] <= bp.COMFORT_Z[0][1] else -.15
        score = min(cap - float(np.linalg.norm(opts[0][1])), .6) + comfortable
        score += 2 if dt >= bp.T_OK else 2 * dt / bp.T_OK - 1
        if best is None or score > best[0]:
            best = (score, i, opts)
    if best is None:
        return None
    _, i, opts = best
    return dict(t=float(ts[i]), pos=positions[i], normal=opts[0][0], vel=opts[0][1], target=target,
                opts=opts[1:], smash=intent["shot"] == "smash", switched=ref.t_min is not None)


class TacticalPlayer:
    """Keep reference execution active while online preferences change between strokes."""

    def __init__(self, spec, reference_class):
        self.bp = sys.modules[reference_class.__module__]
        # Placement randomness is independent of the private environment seed.
        self.reference = reference_class(spec, "A", 0)
        self.home = list(self.reference.wait_xy)
        self.point = None
        self.intent = None
        self.intent_id = None
        self.flight_intent = None
        self.flight_intent_id = None
        self.locked_flight = None
        self.selection = None

    def reset_point(self, point):
        self.point = point
        self.intent = self.intent_id = None
        self.flight_intent = self.flight_intent_id = self.locked_flight = None
        self.reference.wait_xy = list(self.home)
        self.reference.flight, self.reference.plan, self.reference.sent = None, None, None
        self.reference.obs = []
        self.reference.t_min = self.reference.moved = None

    def accept(self, intent, request_id):
        self.intent, self.intent_id = intent, request_id

    def act(self, view):
        state = view["state"]
        if state["point"] != self.point:
            self.reset_point(state["point"])
        self.selection = None
        ref, bp = self.reference, self.bp
        if state.get("ball_state") == "going to the opponent":
            recovery = self.home if self.intent is None else self.intent["recovery"]
            if recovery != ref.wait_xy:
                ref.wait_xy = list(recovery)
                ref.moved = None
        previous = ref.plan
        command = ref.act(view)
        if command is None:
            return None
        if command["type"] == "move":
            self.selection = {"kind": "recovery", "intent_id": self.intent_id,
                              "changed_from_rule": command["base"] != self.home}
        elif (command["type"] == "act" and state.get("ball_state") == "coming to you"
              and ref.plan is not previous and not ref.plan.get("skip")):
            if ref.flight != self.locked_flight:
                self.locked_flight = ref.flight
                self.flight_intent, self.flight_intent_id = self.intent, self.intent_id
            rule = ref.plan
            preferred = None if self.flight_intent is None else _preferred(bp, ref, state, self.flight_intent)
            self.selection = {"kind": "rally", "intent_id": self.flight_intent_id,
                              "rule_target": rule["target"].tolist(),
                              "preferred_status": "not_requested" if self.flight_intent is None else (
                                  "selected" if preferred is not None else "no_screened_candidate"),
                              "changed_from_rule": False}
            if preferred is not None:
                self.selection["changed_from_rule"] = any(
                    not np.allclose(preferred[key], rule[key]) for key in ("target", "normal", "vel"))
                ref.plan = preferred
                contact_frame = round(preferred["t"] * 100)
                ref.sent = {"k_c": contact_frame, "checked": False}
                command = {"type": "act", "t": (contact_frame - state["step"]) / 100,
                           **{key: [round(float(x), 4) for x in preferred[key]] for key in ("pos", "normal", "vel")}}
            self.selection["selected_target"] = ref.plan["target"].tolist()
        return command
