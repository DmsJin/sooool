"""Continuous camera control with persistent, conditional SOL tactics.

The reference owns serving and recovery mechanics. This player owns incoming
flight tracking, early interception moves and contact corrections. SOL chooses
placement and recovery; it never supplies a time-sensitive racket command.
"""

from __future__ import annotations

import base64
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

from . import public as badminton
from .public import _unique_object


POLICY_ROOT = Path(__file__).resolve().parents[2] / "policies/badminton/tactical-goal-v2"
SCHEMA = json.loads((POLICY_ROOT / "schema.json").read_text())
CHOICE_SCHEMA = SCHEMA["properties"]["normal"]
BRANCHES = ("normal", "under_pressure", "opponent_back")
PROMPT = (POLICY_ROOT / "prompt.txt").read_text()


def decode_intent(text, spec):
    """Validate a conditional strategy at the model response boundary."""
    value = json.loads(text, object_pairs_hook=_unique_object)
    if not isinstance(value, dict) or set(value) != set(SCHEMA["required"]):
        raise ValueError("Tactical response requires three branches, recovery, horizon_game_s and memory")
    for branch in BRANCHES:
        choice = value[branch]
        if not isinstance(choice, dict) or set(choice) != {"side", "shot"}:
            raise ValueError(f"{branch} requires side and shot")
        for key in ("side", "shot"):
            if choice[key] not in CHOICE_SCHEMA["properties"][key]["enum"]:
                raise ValueError(f"Invalid {branch}.{key}")
    recovery = value["recovery"]
    if not isinstance(recovery, list) or len(recovery) != 2:
        raise ValueError("Recovery requires two coordinates")
    for axis, coordinate in zip(("x", "y"), recovery):
        lo, hi = spec["base"]["range"][axis]
        if type(coordinate) not in (int, float) or not math.isfinite(coordinate) or not lo <= coordinate <= hi:
            raise ValueError(f"Recovery {axis} outside the public base range")
    horizon = value["horizon_game_s"]
    if type(horizon) not in (int, float) or not math.isfinite(horizon) or not 1 <= horizon <= 10:
        raise ValueError("horizon_game_s must be between 1 and 10 game seconds")
    if not isinstance(value["memory"], str) or len(value["memory"]) > 1200:
        raise ValueError("Memory must be a string of at most 1200 characters")
    return value


def format_prompt(snapshot):
    """Combine the conditional goal task with its public snapshot."""
    public = badminton.public_data({key: value for key, value in snapshot.items() if key != "images"})
    return PROMPT + json.dumps(public, separators=(",", ":"), allow_nan=False)


def _contacts(bp, ref, state, times, positions):
    """Rank interception points; approximate travel time is a cost, not a veto."""
    now = state["step"] * bp.STEP + (ref.lead + 2) * bp.STEP
    base = np.asarray(state["robot_base_xy"])
    candidates = []
    for index in range(0, len(times), 5):
        p, remaining = positions[index], times[index] - now
        if (remaining < .22 or not bp.Z_MIN <= p[2] <= bp.Z_KILL
                or not -(bp.COURT_Y + .7) <= p[1] < -.35 or abs(p[0]) > bp.COURT_X + .9):
            continue
        travel = bp.base_time(float(np.linalg.norm(bp.stance(p) - base)), ref.vmax, ref.amax)
        cost = 4 * max(0., travel + .12 - remaining) + abs(float(p[2]) - 1.25)
        candidates.append((cost, index))
    return [index for _, index in sorted(candidates)]


def _goal(bp, choice):
    return np.array([{"left": -1, "center": 0, "right": 1}[choice["side"]] * .75 * bp.COURT_X,
                     {"clear": .85 * bp.COURT_Y, "drop": .75 * bp.SHORT_Y,
                      "smash": .5 * bp.COURT_Y}[choice["shot"]]])


def _fixed_choice(bp, ref, opp, candidates, times, positions, now):
    side = -1 if opp[0] > 0 else 1
    if ref.rng.random() >= bp.OPEN_P:
        side = -side
    high = any(bp.KILL_Z <= positions[i, 2] <= bp.Z_KILL and times[i] - now >= bp.T_OK for i in candidates)
    return {"side": "left" if side < 0 else "right",
            "shot": "smash" if high else "drop" if opp[1] > bp.BACK_Y else "clear"}


def _placement(bp, choice, target, landing, normal):
    error = float(np.linalg.norm(np.asarray(landing) - target))
    shape = (landing[1] >= .65 * bp.COURT_Y if choice["shot"] == "clear" else
             landing[1] <= 1.25 * bp.SHORT_Y if choice["shot"] == "drop" else normal[2] < 0)
    return {"predicted_landing": list(landing), "target_error_m": error,
            "goal_status": "exact" if error <= .25 and shape else "projected"}


def _flights(bp, positions, incoming, normals, speeds, dt):
    """Batch public drag flights in their horizontal planes, interpolating net and floor crossings."""
    launch = bp.GAIN * speeds + bp.E_IN * np.maximum(0., -np.sum(incoming * normals, axis=1))
    horizontal = np.linalg.norm(normals[:, :2], axis=1)
    heading = normals[:, :2] / horizontal[:, None]
    vh, vz = launch * horizontal, launch * normals[:, 2]
    h, z = np.zeros(len(speeds)), positions[:, 2].copy()
    net_distance = -positions[:, 1] / heading[:, 1]
    net = np.full(len(speeds), np.nan)
    distance = np.full(len(speeds), np.nan)
    alive = np.ones(len(speeds), dtype=bool)
    for _ in range(round(4 / dt)):
        drag = bp.K * np.hypot(vh, vz)
        vh1, vz1 = vh * (1 - drag * dt), vz - (bp.G + drag * vz) * dt
        h1, z1 = h + vh1 * dt, z + vz1 * dt
        cross = alive & (h < net_distance) & (h1 >= net_distance)
        net[cross] = z[cross] + (net_distance[cross] - h[cross]) / (h1[cross] - h[cross]) * (z1[cross] - z[cross])
        floor = alive & (z1 <= 0)
        distance[floor] = h[floor] + z[floor] / (z[floor] - z1[floor]) * (h1[floor] - h[floor])
        alive &= ~floor
        h, z, vh, vz = h1, z1, vh1, vz1
        if not alive.any():
            break
    return positions[:, :2] + distance[:, None] * heading, net - bp.NET_TOP


def _goal_search(bp, ref, state, choice, prediction, original=None, *, target=None,
                 contact_time=None, min_contact=None, base=None, height_range=(.65, 2.95)):
    """Propose a public flight; native robot rehearsals decide whether to install it.

    Coarse contacts span the window at 50 ms, refined at native 10 ms resolution.
    Travel and ready-pose estimates rank proposals without claiming delivery.
    """
    times, positions, velocities = prediction
    target = _goal(bp, choice) if target is None else np.asarray(target)
    now = state["step"] * bp.STEP + (ref.lead + 2) * bp.STEP
    valid = np.flatnonzero((times - now >= .22) & (positions[:, 2] >= height_range[0])
                          & (positions[:, 2] <= height_range[1])
                          & (positions[:, 1] >= -(bp.COURT_Y + .7)) & (positions[:, 1] < -.35)
                          & (abs(positions[:, 0]) <= bp.COURT_X + .9))
    valid = valid[abs(times[valid] - np.round(times[valid] * 100) / 100) <= bp.DT * .51]
    if contact_time is not None:
        valid = valid[np.round(times[valid] * 100) == round(contact_time * 100)]
    if min_contact is not None:
        valid = valid[times[valid] >= min_contact]
    if not len(valid):
        return None
    contacts = np.unique(np.r_[valid[::5], valid[-1], valid[np.argmax(positions[valid, 2])]])
    current_base = np.asarray(state["robot_base_xy"])

    def score(indices, normals, speeds, dt):
        # Camera and delivery errors hurt short shots disproportionately. Check a slower, lower launch too.
        horizontal = np.linalg.norm(normals[:, :2], axis=1)
        lower_pitch = np.arctan2(normals[:, 2], horizontal) - np.radians(2.)
        lower = np.column_stack((normals[:, :2] * (np.cos(lower_pitch) / horizontal)[:, None], np.sin(lower_pitch)))
        remaining = times[indices] - now
        ready_speed = np.clip(2.2 * remaining - .2, .6, bp.HEAD_MAX)
        # This search proposes flights. The native rehearsal decides deliverability.
        delivered = speeds
        upper = speeds
        all_lands, all_clearances = _flights(
            bp, np.tile(positions[indices], (3, 1)), np.tile(velocities[indices], (3, 1)),
            np.vstack((normals, lower, normals)), np.r_[delivered, delivered * .85, upper], dt)
        land, weak_land, strong_land = np.split(all_lands, 3)
        clearance, weak_clearance, _ = np.split(all_clearances, 3)
        legal = (np.isfinite(land).all(axis=1) & (clearance >= .10)
                 & (weak_clearance >= .10) & (weak_land[:, 1] > 0)
                 & (abs(strong_land[:, 0]) <= bp.COURT_X) & (strong_land[:, 1] <= bp.COURT_Y)
                 & (abs(land[:, 0]) <= bp.COURT_X - .04) & (land[:, 1] >= .04)
                 & (land[:, 1] <= bp.COURT_Y - .04))
        unique, inverse = np.unique(indices, return_inverse=True)
        travel = np.array([bp.base_time(float(np.linalg.norm(
            (bp.stance(positions[i]) if base is None else base) - current_base)), ref.vmax, ref.amax)
                           for i in unique])[inverse]
        errors = np.sum(((land - target) / [bp.COURT_X, bp.COURT_Y]) ** 2, axis=1)
        risk = (8 * np.maximum(0., travel + .12 - remaining) ** 2
                + 2 * np.maximum(0., bp.T_OK - remaining) ** 2
                + .3 * np.maximum(0., speeds - ready_speed) ** 2
                + .15 * np.maximum(0., positions[indices, 2] - 1.75) ** 2)
        # A smash's downward trajectory remains a preference, not a reason to refuse a low incoming ball.
        if choice["shot"] == "smash":
            errors += .3 * np.maximum(0., normals[:, 2]) ** 2
        costs = errors + risk + .005 * speeds ** 2
        return np.where(legal, costs, np.inf), land, clearance

    ci, elevation, azimuth, speed = np.meshgrid(contacts, np.arange(-20., 81., 5.),
                                               [-12., 0., 12.], np.arange(.2, 2.401, .2), indexing="ij")

    def normals_at(indices, elevations, azimuths):
        direction = target - positions[indices, :2]
        yaw = np.arctan2(direction[:, 0], direction[:, 1]) + np.radians(azimuths)
        pitch = np.radians(elevations)
        return np.column_stack((np.sin(yaw) * np.cos(pitch), np.cos(yaw) * np.cos(pitch), np.sin(pitch)))

    ci, elevation, azimuth, speed = (a.ravel() for a in (ci, elevation, azimuth, speed))
    normals = normals_at(ci, elevation, azimuth)
    costs, _, _ = score(ci, normals, speed, .01)
    best = int(np.argmin(costs))
    # Refine the best region even when coarse sampling narrowly misses the court or net constraint.
    if not np.isfinite(costs[best]):
        if original is None:
            return None
        best = int(np.argmin(abs(times[ci] - original["t"])))
    center = ci[best]
    fine_contacts = valid[abs(times[valid] - times[center]) <= .051]
    fi, fe, fa, fs = np.meshgrid(fine_contacts, elevation[best] + np.arange(-5., 5.01, 2.5),
                                azimuth[best] + np.arange(-6., 6.01, 3.),
                                np.clip(speed[best] + np.arange(-.2, .201, .1), .05, bp.HEAD_MAX), indexing="ij")
    fi, fe, fa, fs = (a.ravel() for a in (fi, fe, fa, fs))
    fn = normals_at(fi, fe, fa)
    # The fixed policy supplies an independently solved candidate, not an anchor for the contact search.
    fi, fn, fs = np.r_[fi, ci[best]], np.vstack((fn, normals[best])), np.r_[fs, speed[best]]
    if original is not None:
        fi = np.r_[fi, int(np.argmin(abs(times - original["t"])))]
        fn = np.vstack((fn, original["normal"]))
        fs = np.r_[fs, float(np.linalg.norm(original["vel"]))]
    costs, landings, clearances = score(fi, fn, fs, bp.DT)
    best = int(np.argmin(costs))
    if not np.isfinite(costs[best]):
        return None
    i, normal, speed = fi[best], fn[best], fs[best]
    landing = landings[best]
    return dict(t=float(times[i]), pos=positions[i], normal=normal, vel=speed * normal,
                target=target,
                goal_choice=dict(choice), **_placement(bp, choice, target, landing, normal),
                net_clearance_m=float(clearances[best]),
                delivery={"preparation_s": float(times[i] - now),
                          "base_travel_s": bp.base_time(float(np.linalg.norm(
                              (bp.stance(positions[i]) if base is None else base) - current_base)), ref.vmax, ref.amax),
                          "requested_head_speed_mps": float(speed),
                          "predicted_head_speed_mps": float(speed),
                          "ready_head_speed_estimate_mps": bp.head_cap(float(times[i] - now))},
                incoming=velocities[i], **({} if base is None else {"base": np.asarray(base)}))


class TacticalPlayer:
    """Execute camera interception continuously and apply SOL only to new strokes."""

    def __init__(self, spec, reference_class):
        self.bp = sys.modules[reference_class.__module__]
        self.reference = reference_class(spec, "A", 0)
        self.spec = spec
        self.home = list(self.reference.wait_xy)
        self.point = None
        self.intent = self.intent_id = None
        self.intent_expires = None
        self.selection = self.feedback = self.action_feedback = None
        self.intercepted = None
        self.candidates = []
        self.pending = self.last_ack = self.retry_after = None

    def reset_point(self, point):
        self.point = point
        self.pending = self.last_ack = self.retry_after = None
        self.candidates = []
        self.intent = self.intent_id = self.intent_expires = None
        self.intercepted = None
        ref = self.reference
        ref.wait_xy = list(self.home)
        ref.flight, ref.plan, ref.sent = None, None, None
        ref.obs = []
        ref.t_min = ref.moved = None
        self.selection = self.feedback = self.action_feedback = None

    def accept(self, intent, request_id, *, source_game_time=0.):
        self.intent, self.intent_id = intent, request_id
        self.intent_expires = source_game_time + intent["horizon_game_s"]

    def _command(self, state, plan):
        self.selection = {**plan["selection"], **{key: plan[key] for key in (
            "goal_status", "predicted_landing", "target_error_m", "net_clearance_m", "delivery") if key in plan},
            "selected_target": plan["target"].tolist()}
        self.feedback.update({key: self.selection[key] for key in (
            "requested_choice", "requested_target", "goal_status", "predicted_landing", "target_error_m", "delivery")
            if key in self.selection})
        contact_frame = round(plan["t"] * 100)
        return {"type": "act", "t": (contact_frame - state["step"]) / 100,
                **{key: [round(float(x), 4) for x in plan[key]] for key in ("pos", "normal", "vel")}}

    def acknowledge(self, ack):
        """Only an installed, rehearsed candidate becomes the active stroke."""
        if ack is None or ack["point"] != self.point or ack["source_frame"] == self.last_ack:
            return
        self.last_ack = ack["source_frame"]
        self.pending = None
        if ack["status"] == "installed":
            plan = dict(ack["plan"])
            for key in ("pos", "normal", "vel", "target", "incoming", "base"):
                if key in plan:
                    plan[key] = np.asarray(plan[key])
            self.reference.plan = plan
            self.retry_after = None
        else:
            self.retry_after = ack["earliest_contact"] + .10

    def _propose(self, state, plan, prediction):
        """Offer bounded alternatives without changing the installed stroke."""
        bp, ref = self.bp, self.reference
        plans = [plan]
        current = np.asarray(state["robot_base_xy"])
        min_contact = self.retry_after
        if "replaces_contact" in plan:
            min_contact = (plan["replaces_contact"] if min_contact is None else
                           max(plan["replaces_contact"], min_contact))
        comfortable = _goal_search(bp, ref, state, plan["goal_choice"], prediction,
            target=plan["target"], height_range=(1.1, 1.6),
            min_contact=min_contact)
        if comfortable is None:
            comfortable = _goal_search(bp, ref, state, plan["goal_choice"], prediction,
                target=plan["target"], min_contact=plan["t"] + .15)
        anchor = comfortable if comfortable is not None else plan
        stance = current + .75 * (bp.stance(anchor["pos"]) - current)
        held = _goal_search(bp, ref, state, plan["goal_choice"], prediction,
                            target=plan["target"], contact_time=anchor["t"], base=stance,
                            min_contact=min_contact)
        for alternative in (held, comfortable):
            if alternative is not None:
                alternative["selection"] = dict(plan["selection"])
                if "replaces_contact" in plan:
                    alternative["replaces_contact"] = plan["replaces_contact"]
                plans.append(alternative)
        self.candidates = plans
        self.pending = state["step"]
        return self._command(state, plan)

    def _rally(self, view):
        ref, bp, state = self.reference, self.bp, view["state"]
        started = time.perf_counter()
        now = state["step"] * bp.STEP
        t0 = round(now - state["t_since_played"], 3)
        flight = (state["point"], t0)
        if ref.flight != flight:
            self.pending = self.retry_after = None
            ref.flight, ref.plan, ref.sent = flight, None, None
            ref.obs, ref.t_min = [], None
        observation = view["observation"]
        seen = {round(t, 3) for t, _ in ref.obs}
        img = bp.decode(base64.b64decode(observation["image_png_b64"]))
        for at, position in bp.detect_views(img, ref.cams, observation["view_sim_times"]):
            if at > t0 + .005 and round(at, 3) not in seen:
                ref.obs.append((at, position))
                seen.add(round(at, 3))
        self.feedback = {"repaired": False, "reason": "insufficient_observations"}
        if len(ref.obs) < 2 or ref.obs[-1][0] - ref.obs[0][0] < .05:
            return None
        at, position, velocity, error = bp.fit(ref.obs)
        self.feedback.update(fit_rms_m=error, observations=len(ref.obs), newest_sample_time=ref.obs[-1][0])
        if error > .08:
            ref.obs = ref.obs[-4:]
            self.feedback["reason"] = "inconsistent_fit"
            return None
        prediction = bp.predict(position, velocity, at)
        times, positions, velocities = prediction
        land = positions[-1]
        if len(ref.obs) >= 4 and land[2] <= .05 and (abs(land[0]) > bp.COURT_X + bp.OUT_MARGIN or land[1] < -bp.COURT_Y - bp.OUT_MARGIN):
            self.feedback["reason"] = "predicted_out"
            return None
        candidates = _contacts(bp, ref, state, times, positions)
        if ref.plan is None and self.intercepted != flight and candidates and len(ref.obs) < 4:
            # Use early measurements for movement without postponing a stroke once four samples are available.
            self.intercepted = flight
            interception = candidates[0] if any(times[i] - now >= bp.T_OK for i in candidates) else max(
                candidates, key=lambda i: times[i])
            base = bp.stance(positions[interception])
            base = [round(float(np.clip(x, *self.spec["base"]["range"][axis])), 4)
                    for axis, x in zip(("x", "y"), base)]
            self.feedback.update(reason="early_interception", selected_contact_frame=round(times[interception] * 100))
            self.selection = {"kind": "interception", "intent_id": None, "changed_from_rule": True}
            return {"type": "move", "base": base}
        if len(ref.obs) < 4:
            return None
        if self.pending is not None:
            self.feedback["reason"] = "awaiting_rehearsal"
            return None
        plan = ref.plan
        if plan is not None:
            remaining = plan["t"] - now
            index = int(np.argmin(abs(times - plan["t"])))
            shift = float(np.linalg.norm(positions[index] - plan["pos"]))
            self.feedback.update(contact_frame=round(plan["t"] * 100), remaining_s=remaining,
                                 contact_shift_m=shift, predicted_contact=positions[index].tolist())
            if remaining <= bp.LAST_REFINE_S:
                self.feedback["reason"] = "contact_committed"
                return None
            if shift < .03:
                self.feedback["reason"] = "contact_stable"
                return None
            # Repair geometry at the same contact first; every replacement is rehearsed.
            replacement = _goal_search(bp, ref, state, plan["goal_choice"], prediction,
                                       target=plan["target"], contact_time=plan["t"],
                                       base=plan.get("base"), min_contact=self.retry_after)
            if replacement is None:
                min_contact = plan["t"] + .15
                if self.retry_after is not None:
                    min_contact = max(min_contact, self.retry_after)
                replacement = _goal_search(bp, ref, state, plan["goal_choice"], prediction,
                                           target=plan["target"], min_contact=min_contact)
            if replacement is None:
                self.feedback["reason"] = "no_repair_keep_swing"
                return None
            replacement["selection"] = dict(plan["selection"])
            replacement["replaces_contact"] = plan["t"]
            self.feedback.update(repaired=True, reason="contact_repair",
                                 selected_contact_frame=round(replacement["t"] * 100))
            return self._propose(state, replacement, prediction)
        opp = bp.backtrack(position, velocity, max(0., at - t0))[:2]
        fixed_choice = _fixed_choice(bp, ref, opp, candidates, times, positions, now)
        rule = _goal_search(bp, ref, state, fixed_choice, prediction, min_contact=self.retry_after)
        if fixed_choice["shot"] == "smash" and (rule is None or rule["goal_status"] != "exact"):
            fixed_choice = {**fixed_choice, "shot": "drop" if opp[1] > bp.BACK_Y else "clear"}
            rule = _goal_search(bp, ref, state, fixed_choice, prediction, min_contact=self.retry_after)
        branch = "under_pressure" if not any(times[i] - now >= bp.T_OK for i in candidates) else (
            "opponent_back" if opp[1] > bp.BACK_Y else "normal")
        choice = self.intent[branch] if self.intent is not None else fixed_choice
        target = _goal(bp, choice)
        preferred = rule if self.intent is None or choice == fixed_choice else _goal_search(
            bp, ref, state, choice, prediction, rule, min_contact=self.retry_after)
        plan = preferred if preferred is not None else rule
        self.feedback.update(reason="stroke_selected" if plan is not None else "placement_unavailable",
                             search_seconds=time.perf_counter() - started)
        if plan is None:
            return None
        plan["selection"] = {"kind": "rally", "stroke_id": list(flight), "intent_id": self.intent_id, "branch": branch,
                          "requested_choice": dict(choice), "requested_target": target.tolist(),
                          "goal_origin": "sol" if self.intent is not None else "fixed",
                          "rule_target": None if rule is None else rule["target"].tolist(),
                          "preferred_status": "not_requested" if self.intent is None else (
                              "selected" if preferred is not None else "placement_unavailable"),
                          "changed_from_rule": preferred is not None and (rule is None or any(
                              not np.allclose(preferred[key], rule[key]) for key in ("t", "pos", "normal", "vel"))),
                          "selected_target": plan["target"].tolist()}
        if preferred is None:
            plan["goal_status"] = "rule_fallback"
            plan["goal_choice"], plan["target"] = dict(choice), target
        return self._propose(state, plan, prediction)

    def act(self, view):
        state = view["state"]
        if state["point"] != self.point:
            self.reset_point(state["point"])
        self.selection = self.feedback = self.action_feedback = None
        self.candidates = []
        if self.intent_expires is not None and state["step"] / 100 >= self.intent_expires:
            self.intent = self.intent_id = self.intent_expires = None
        ref = self.reference
        if state["ball_state"] == "going to the opponent":
            recovery = self.home if self.intent is None else self.intent["recovery"]
            if recovery != ref.wait_xy:
                ref.wait_xy = list(recovery)
                ref.moved = None
        if state["ball_state"] == "coming to you" and state["t_since_played"] is not None:
            return self._rally(view)
        command = ref.act(view)
        if command is not None and command["type"] == "move":
            self.selection = {"kind": "recovery", "intent_id": self.intent_id,
                              "changed_from_rule": command["base"] != self.home}
        return command
