"""Small frozen shot policies selected by SOL over continuous reference execution."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

from environments.badminton.public import _unique_object, public_data

POLICY_ROOT = Path(__file__).resolve().parents[2] / "policies/tabletennis/tactical-v1"
SCHEMA = json.loads((POLICY_ROOT / "schema.json").read_text())
PROMPT = (POLICY_ROOT / "prompt.txt").read_text()
POLICIES = {
    "reference": None,
    "safe_center": (0.0, 0.4, (3.8, 3.4, 3.0, 2.6)),
    "wide_left": (-0.30, 0.45, (3.8, 3.4, 3.0)),
    "wide_right": (0.30, 0.45, (3.8, 3.4, 3.0)),
    "short_center": (0.0, 0.25, (3.4, 3.0, 2.6)),
}


def decode_intent(text):
    intent = json.loads(text, object_pairs_hook=_unique_object)
    if not isinstance(intent, dict) or set(intent) != {"policy", "memory", "decision_summary"}:
        raise ValueError("Expected policy, memory and decision_summary")
    if not isinstance(intent["policy"], str) or intent["policy"] not in SCHEMA["properties"]["policy"]["enum"]:
        raise ValueError("Unknown tactical policy")
    if not isinstance(intent["memory"], str) or len(intent["memory"]) > 1200:
        raise ValueError("Memory must be a string of at most 1200 characters")
    if not isinstance(intent["decision_summary"], str) or not 1 <= len(intent["decision_summary"]) <= 220:
        raise ValueError("Decision summary must contain 1..220 characters")
    return intent


def format_prompt(snapshot):
    return PROMPT + json.dumps(public_data(snapshot), separators=(",", ":"), allow_nan=False)


class TacticalPlayer:
    def __init__(self, spec, reference_class):
        self.reference = reference_class(spec, "A", 0)
        self.bp = sys.modules[reference_class.__module__]
        self.intent = ("safe_center", None)
        self.locked_leg = None
        self.flight_intent = self.intent
        self.selection = None
        self.rule_stroke = self.reference.P.stroke
        self.rule_decide = self.reference.P.decide
        self.reference.P.stroke = self.stroke
        self.reference.P.decide = self.decide
        # Incoming tangential speed need not be copied by the paddle: the public
        # normal restitution law already preserves it. This avoids a large,
        # mechanically expensive upward brush on short returns.
        self.reference.P.tangential = False
        self.bp.SERVE_LATE = True
        self.bp.SHORT_Z = .24
        self.reference._serve = lambda state, clock: self.serve(state)
        self.serve_request = None
        self.service_plan = None

    def serve(self, state):
        """One preplanned stroke and an absolute toss deadline, not two moving targets."""
        ref, bp = self.reference, self.bp
        sv, point = state.get("serve") or {}, state["point"]
        if ref.srv is None or ref.srv["point"] != point:
            ref.srv = {"point": point, "tossed": False, "acted": False}
        service = ref.srv
        # One conservative forehand service, without the repertoire's spin brush.
        toss, original = self.service_plan
        base = original["base"]
        if sv.get("phase") in ("waiting", "open") and not service["acted"]:
            if np.max(np.abs(ref.base_rest - base)) > 1e-6:
                ref.base_rest = base.copy()
                return {"type": "move", "base": base.tolist()}
            if sv.get("phase") != "open" or not ref._settled(state, base):
                return None
            # Give the worker time before installing the wind-up. Toss and
            # contact are on the same native clock even if rendering is late.
            projection_frames = round(original["t_from_projection"] * 100)
            toss_frame = state["step"] + 75
            contact_frame = toss_frame + bp.TOSS_REST + projection_frames
            position, incoming = bp.toss_flight(np.array(toss["pos"]), bp.toss_speed(toss["height"]),
                                               projection_frames / 100)
            center, normal, velocity = bp.paddle_for(position, incoming, original["v_out"], False)
            service["acted"] = service["tossed"] = True
            self.serve_request = {"toss": {"type": "toss", **toss}, "toss_frame": toss_frame,
                                  "contact_frame": contact_frame}
            return {"type": "act", "t": (contact_frame-state["step"])/100,
                    "pos": center.tolist(), "normal": normal.tolist(), "vel": velocity.tolist(),
                    "base": base.tolist()}
        if sv.get("phase") == "done" and np.max(np.abs(ref.base_rest-ref.home)) > 1e-6:
            ref.base_rest = ref.home.copy()
            return {"type": "move", "base": ref.home.tolist()}
        return None

    def accept(self, intent, request_id):
        # Immutable assignment; the control worker freezes this pair per incoming flight.
        self.intent = (intent["policy"], request_id)

    def context(self, state):
        """Compact facts derived only from public images and public game feedback."""
        leg = self.reference.P.leg
        last_seen = None
        if leg and leg["kind"] != "serve" and leg["frames"]:
            t, position = min(leg["frames"].items())
            if t < .2:
                last_seen = {"x": round(float(position[0]), 2),
                             "age_game_seconds": round((state["step"]-leg["launch"])/100-t, 2)}
        return {"opponent_last_seen_at_strike": last_seen,
                "current_flight_policy": self.flight_intent[0],
                "next_flight_policy": self.intent[0],
                "ball_phase": state["ball_state"], "recent_outcomes": state.get("shots", []),
                "shot_targets": {name: {"x": choice[0], "y": choice[1]}
                                 for name, choice in POLICIES.items() if choice is not None}}

    def decide(self, clock):
        """Commit a stroke; permit one correction once three post-bounce frames exist."""
        leg = self.reference.P.leg
        if leg and leg["acts"]:
            if leg["acts"][-1]["phase"] == "post":
                return None
            bounces = [event["t"] for event in leg["heard"]
                       if event["event"] == "bounce on your half"]
            if not bounces or sum(t > bounces[0] + .003 for t in leg["frames"]) < 3:
                return None
        return self.rule_decide(clock)

    def stroke(self, position, incoming, vp_max=None):
        player, bp = self.reference.P, self.bp
        key = player.leg["key"]
        if key != self.locked_leg:
            self.locked_leg, self.flight_intent = key, self.intent
        policy, request_id = self.flight_intent
        self.selection = {"policy": policy, "intent_id": request_id, "selected": False}
        choice = POLICIES[policy]
        if choice is not None:
            x, y, speeds = choice
            aim = np.array([x, y])
            cap = player.vp_max if vp_max is None else vp_max
            from .perception import countershot
            feasible, normal, velocity, outgoing = countershot(np.asarray(position,float), np.asarray(incoming,float),
                                                              aim, bp.G, bp.KD)
            if feasible:
                center = np.asarray(position)-bp.OFFSET*normal
                player._chosen = (float(outgoing[1]),float(np.sign(x)))
                self.selection.update(selected=True, target=aim.tolist(), blade_speed=float(np.linalg.norm(velocity)),
                    reference_speed_cap=cap, incoming_velocity=np.asarray(incoming).tolist(),
                    outgoing_velocity=outgoing.tolist(), contact_ball=np.asarray(position).tolist(),
                    contact_solver="joint face/speed flight screening")
                return center,normal,velocity,aim
            best = None
            for speed in speeds:
                outgoing, clear = bp.solve_out(position, aim, speed)
                if not clear:
                    continue
                center, normal, velocity = bp.paddle_for(position, incoming, outgoing, player.tangential)
                blade_speed = float(np.linalg.norm(velocity))
                if best is None or blade_speed < best[0]:
                    best = (blade_speed, speed, center, normal, velocity, outgoing)
                if blade_speed <= cap:
                    break
            if best is not None:
                # Match Player.stroke: vp_max ranks candidates; it is not the native
                # action limit. Native planning rehearses and scales mechanical delivery.
                blade_speed, speed, center, normal, velocity, outgoing = best
                player._chosen = (speed, float(np.sign(x)))
                self.selection.update(selected=True, target=aim.tolist(),
                                      blade_speed=blade_speed, reference_speed_cap=cap,
                                      incoming_velocity=np.asarray(incoming).tolist(),
                                      outgoing_velocity=outgoing.tolist(), contact_ball=np.asarray(position).tolist())
                return center, normal, velocity, aim
            self.selection["fallback"] = "no_screened_candidate"
        return self.rule_stroke(position, incoming, vp_max)

    def act(self, view):
        self.selection = None
        self.serve_request = None
        action = self.reference.act(view)
        if action is not None and self.selection is not None:
            ball = self.selection["contact_ball"]
            action["base"] = [float(np.clip(ball[0],-.65,.65)),
                              float(np.clip(ball[1]-.45,-2.2,-1.58))]
        return action, self.selection
