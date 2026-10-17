"""Run paced physics independently of camera control, stroke planning and paid inference."""
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from collections import deque
import base64
from decimal import Decimal
import json
import math
import multiprocessing
from pathlib import Path
import queue
import signal
import statistics
import threading
import time
import random
import sys

import numpy as np

from .api import TacticalAPI, realtime_prompt
from .public import native_action, public_data, public_spec
from .runner import _write, _sample_delays
from .tactics import TacticalPlayer, _flights, _placement, decode_intent, format_prompt, POLICY_ROOT, SCHEMA
from environments.touhou.research.budget import BudgetError

_player = _renderer = _sport = _planner = None


def _start_control(spec, cfg):
    # Native imports require the external environment; pure contract tests do not.
    from .native import load_sport
    global _player, _renderer, _sport
    _sport = load_sport()
    _player = TacticalPlayer(spec, _sport.players()["reference"])
    _renderer = _sport.worker_init("render", "A", cfg)
    _control.spec = spec
    _control.slowdown = cfg.slowdown


def _control(job, state, metadata, intent, intent_id, intent_source_frame, memory, history, profile, directory, captured):
    start = time.monotonic()
    png = _sport.worker_call(_renderer, "render", job)["png"]
    image = Path(directory) / "images" / f'frame-{state["step"]:07d}.png'
    image.write_bytes(png)
    if state["point"] != _player.point:
        _player.reset_point(state["point"])
    _player.acknowledge(state["control_ack"])
    if intent is not None and intent_id != _player.intent_id:
        _player.accept(intent, intent_id, source_game_time=intent_source_frame / 100)
    command = _player.act({"state": state, "observation": {"image_png_b64": base64.b64encode(png).decode(), **metadata}})
    if command is not None and command["type"] == "act":
        command = dict(command)
        # Goal commands already name the absolute contact relative to this observation.
        # Native reference serving commands name preparation after the mechanical lead.
        lead = 0 if _player.selection is not None and _player.selection["kind"] == "rally" else _player.reference.lead
        command["contact_at_game_time"] = (state["step"] + lead + round(command.pop("t") * 100)) / 100
    candidates = []
    for plan in _player.candidates:
        plan = {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in plan.items()}
        candidate = {"type": "act", "contact_at_game_time": round(plan["t"] * 100) / 100,
                     **{k: plan[k] for k in ("pos", "normal", "vel", "base") if k in plan}}
        candidates.append({"command": candidate, "plan": plan})
    snapshot = {"frame": state["step"], "game_time": state["step"] / 100,
                "state": public_data(state), "spec": public_spec(_control.spec),
                "camera_metadata": public_data(metadata), "images": [{"path": str(image), "frame": state["step"]}],
                "intent": _player.intent, "intent_id": _player.intent_id,
                "memory": memory, "action_history": history, "feedback": _player.feedback,
                "latency": {"slowdown": _control.slowdown, "capacity": 1, "clock": "native_scheduler",
                            "profile_summary": profile["summary"]}}
    return {"snapshot": snapshot, "command": command, "selection": _player.selection, "candidates": candidates,
            "feedback": _player.feedback,
            "capture_monotonic": captured,
            "local_compute_seconds": time.monotonic() - start}


def _start_planner():
    from .native import load_sport
    global _planner
    _planner = load_sport().worker_init("plan", "A", None)


def _plan(job, candidate=None):
    prepared = _planner.plan(job)
    if candidate is not None and prepared["status"] == "ok":
        prepared["delivery"] = assess_delivery(candidate["plan"], prepared["info"])
    prepared["completed_monotonic"] = time.monotonic()
    return prepared


def assess_delivery(plan, info):
    """Judge a camera-derived flight using only native robot rehearsal feedback."""
    from .native import load_sport
    bp = sys.modules[load_sport().players()["reference"].__module__]
    reasons = []
    if info["blade_error_m"] > .02:
        reasons.append("position")
    if info["normal_error_deg"] > 3:
        reasons.append("normal")
    if "self-collision" in info["stroke"] or "joint-velocity reflex" in info["stroke"]:
        reasons.append("robot_stop")
    normal = np.asarray(plan["normal"])
    speed = max(0., float(np.asarray(info["racket_vel_delivered"]) @ normal))
    horizontal = np.linalg.norm(normal[:2])
    pitch = np.arctan2(normal[2], horizontal)
    normals = np.array([np.r_[normal[:2] / horizontal * np.cos(pitch + angle), np.sin(pitch + angle)]
                        for angle in (0., -np.radians(3), np.radians(3))])
    lands, clearance = _flights(bp, np.tile(plan["pos"], (3, 1)), np.tile(plan["incoming"], (3, 1)),
                               normals, np.array([speed, speed * .90, speed * 1.03]), bp.DT)
    legal = np.isfinite(lands).all() and np.all(clearance >= .10) and np.all(
        (abs(lands[:, 0]) <= bp.COURT_X - .02) & (lands[:, 1] >= .02) & (lands[:, 1] <= bp.COURT_Y - .02))
    if not legal:
        reasons.append("outgoing_flight")
    placement = (_placement(bp, plan["goal_choice"], plan["target"], lands[0], normal)
                 if np.isfinite(lands[0]).all() else {"predicted_landing": None, "target_error_m": None,
                                                    "goal_status": "projected"})
    if plan["goal_status"] == "rule_fallback":
        placement["goal_status"] = "rule_fallback"
    return {"valid": not reasons, "reasons": reasons, "normal_speed_mps": speed,
            **placement, "net_clearance_m": None if not np.isfinite(clearance[0]) else float(clearance[0])}


def _warm_planner():
    return True


def timing_stats(values):
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None, "max": None}
    ordered = sorted(values)
    return {"count": len(values), "mean": statistics.fmean(values), "p50": statistics.median(values),
            "p95": ordered[math.ceil(len(values) * .95) - 1],
            "p99": ordered[math.ceil(len(values) * .99) - 1], "max": ordered[-1]}


def run_realtime(config, recipe, profile, output, *, key, budget_usd, preflight=False,
                 source="sol", mode="realtime", checkpoint=None):
    """Run shared native scheduling with explicit clock and model-provider modes."""
    from .native import Action, BadmintonEnvironment
    from core.sport import Refused, parse_action
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "images").mkdir()
    frames = config["max_game_seconds"] * 100
    period = config["slowdown"] / 100
    env = BadmintonEnvironment(level=config["level"], seed=config["seed"], max_env_steps=frames + 1,
                              slowdown=config["slowdown"])
    state = env.reset(render=False)
    first_frame = 0
    if checkpoint is not None:
        # Offline diagnosis restores the physical prefix; actors still see only cameras.
        env.match.g = sys.modules["wc"].restore(checkpoint["native"], env.match.g.s.m)
        env.env_step = first_frame = env.match.g.k
        state = env.public_state()
    spec = env._spec
    lead = spec["act"]["lead_steps"]
    _write(output / "run.json", {"config": config, "recipe": recipe, "seed": config["seed"],
                                "profile": profile, "preflight": preflight, "window_steps": frames,
                                "source": source, "clock_mode": mode, "first_frame": first_frame})
    context = multiprocessing.get_context("spawn")
    control_pool = ProcessPoolExecutor(1, mp_context=context, initializer=_start_control, initargs=(spec, env._cfg))
    plan_pool = ProcessPoolExecutor(3, mp_context=context, initializer=_start_planner)
    api_pool = ThreadPoolExecutor(1, thread_name_prefix="badminton-api")
    api = None if preflight or source == "rules" or mode == "simulated" else TacticalAPI(
        key, output, budget_usd, recipe, ledger_path=config["ledger_path"])
    subscription = None
    if mode == "simulated" and source != "rules":
        from runtime.subscription import SubscriptionClient
        subscription = SubscriptionClient(output=output / "worker", output_schema=SCHEMA,
            system=(POLICY_ROOT / "system.txt").read_text(), service_tier="default")
    rng = random.Random(42 + config["seed"])
    stopped = threading.Event()
    handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    for s in handlers:
        signal.signal(s, lambda *_: stopped.set())
    published = queue.SimpleQueue()
    control = planning = scheduled = request = None
    commands = deque()
    retired = []
    intent = intent_id = intent_source_frame = None
    if checkpoint is not None:
        intent = checkpoint["intent"]
        intent_id, intent_source_frame = 0, first_frame
    memory, history = "", []
    generation = calls = accepted = invalid = late_plans = late_candidates = discarded = expired = 0
    next_request, request_info = first_frame, None
    ack = None
    initial_results = len(env.match.g.results)
    lag_values, deliveries, compute_values, results, intention_delays = [], [], [], [], []
    log = (output / "events.jsonl").open("w", buffering=1)
    status, reason, error = "interrupted", None, None
    frame, started, elapsed = first_frame, None, 0.0
    metrics = {"points_for": 0, "points_against": 0, "success": False}

    def event(kind, **fields):
        log.write(json.dumps({"event": kind, "frame": frame, **fields}, separators=(",", ":"), allow_nan=False) + "\n")

    def capture():
        captured = time.monotonic()
        job, metadata = env.match.camera_job("A")
        current = env.public_state()
        current["pending_commands"] = bool(commands) or planning is not None or scheduled is not None
        current["control_ack"] = ack
        future = control_pool.submit(_control, job, current, metadata, intent, intent_id, intent_source_frame,
                                     memory, history[-16:], profile, str(output), captured)
        if mode == "simulated":
            future.result()
            future.ready_frame = frame + math.ceil((time.monotonic() - captured) / period)
        return future

    def ready(future, issued):
        if mode == "realtime":
            return future.done()
        result = future.result()
        return frame >= issued["frame"] + math.ceil((result["completed_monotonic"] - issued["monotonic"]) / period)

    def subscribe(snapshot, directory):
        text, metadata = subscription.act(format_prompt(snapshot),
            [Path(snapshot["images"][-1]["path"]).read_bytes()], directory)
        return {"intent": decode_intent(text, spec), "brief": "Subscription conditional strategy.",
                "model_wall_seconds": metadata["wall_seconds"]}

    try:
        # Warm both native workers before starting the measured game clock.
        for warm in [plan_pool.submit(_warm_planner) for _ in range(3)]:
            warm.result()
        initial = capture().result()
        started = time.monotonic()
        event("reset", state=state, planning_lead_steps=lead)
        control = None
        ready_control = initial
        while frame < frames:
            due = started + (frame - first_frame) * period
            remaining = due - time.monotonic()
            if mode == "realtime" and remaining > 0:
                time.sleep(remaining)
            now = time.monotonic()
            elapsed = now - started
            lag = max(0.0, now - due) if mode == "realtime" else 0.
            lag_values.append(lag)
            if stopped.is_set() or Path(config["stop_file"]).exists():
                reason = "stop_requested"
                break
            if mode == "realtime" and elapsed >= config["max_wall_seconds"]:
                reason = "wall_limit"
                break
            if lag > config["lag_max_limit_seconds"]:
                reason = "clock_lag_limit"
                break
            if (mode == "simulated" and request is not None and not request_info["published"]
                    and frame >= request_info["ready_frame"]):
                response = request.result()
                response.update(json_ready_monotonic=now, virtual_delay_seconds=request_info["delay_seconds"])
                published.put((request_info, response))
                results.append({"timing": {"json_ready_seconds": request_info["delay_seconds"],
                                           "terminal_seconds": request_info["service_seconds"]},
                                "model_wall_seconds": response["model_wall_seconds"]})
                request_info["published"] = True
            if (mode == "simulated" and request is not None and request_info["published"]
                    and frame >= request_info["release_frame"]):
                request = None
            while not published.empty():
                origin, response = published.get()
                if origin["generation"] != generation:
                    discarded += 1
                    event("discarded", id=origin["id"], reason="previous_point")
                elif frame >= origin["source_frame"] + response["intent"]["horizon_game_s"] * 100:
                    expired += 1
                    event("discarded", id=origin["id"], reason="expired")
                else:
                    intent, intent_id, memory = response["intent"], origin["id"], response["intent"]["memory"]
                    intent_source_frame = origin["source_frame"]
                    accepted += 1
                    delivery = {"id": intent_id, "source_frame": origin["source_frame"],
                                "point": origin["point"], "intent": intent, "brief": response["brief"],
                                "capture_to_accept_seconds": ((frame - origin["source_frame"]) * period
                                    if mode == "simulated" else now - origin["capture_monotonic"]),
                                "capture_to_accept_game_seconds": (frame - origin["source_frame"]) / 100,
                                "ready_to_accept_seconds": now - response["json_ready_monotonic"],
                                "accepted_monotonic": now, "accepted_frame": frame, **response}
                    deliveries.append(delivery)
                    event("intent_accepted", **delivery)
            if mode == "realtime" and request is not None and request.done():
                finished = request
                request = None
                results.append(finished.result())
            if intent is not None and frame >= intent_source_frame + intent["horizon_game_s"] * 100:
                intent = intent_id = intent_source_frame = None
            for batch, item in list(retired):
                if item["future"].done():
                    prepared = item["future"].result()
                    event("candidate_late", source_frame=batch["source_frame"], candidate=item["index"],
                          command=item["command"], feedback=prepared.get("info"), delivery=prepared.get("delivery"))
                    retired.remove((batch, item))
            if planning is not None:
                completed = [item for item in planning["items"] if ready(item["future"], planning)]
                if frame >= planning["effect_frame"] or len(completed) == len(planning["items"]):
                    late_candidates += len(planning["items"]) - len(completed)
                    retired.extend((planning, item) for item in planning["items"] if item not in completed)
                    valid = []
                    for item in completed:
                        prepared = item["future"].result()
                        delivery = prepared.get("delivery")
                        event("candidate_rehearsed", source_frame=planning["source_frame"],
                              candidate=item["index"], command=item["command"],
                              feedback=prepared.get("info"), delivery=delivery)
                        if prepared["status"] == "ok" and (delivery is None or delivery["valid"]):
                            valid.append({**planning, **item, "prepared": prepared})
                    if planning["generation"] != generation or frame > planning["effect_frame"]:
                        late_plans += 1
                        event("planning_discarded", source_frame=planning["source_frame"],
                              reason="previous_point" if planning["generation"] != generation else "deadline")
                        if planning["generation"] == generation and planning["selection"] is not None:
                            ack = {"point": env.public_state()["point"], "source_frame": planning["source_frame"],
                                   "status": "rejected", "earliest_contact": planning["earliest_contact"]}
                    elif valid:
                        scheduled = min(valid, key=lambda item: (
                            item["prepared"]["delivery"]["target_error_m"]
                            if "delivery" in item["prepared"] else 0))
                    else:
                        late_plans += int(not completed)
                        event("planning_discarded", source_frame=planning["source_frame"],
                              reason="deadline" if not completed else "no_deliverable_candidate")
                        if planning["selection"] is not None and planning["selection"]["kind"] == "rally":
                            ack = {"point": env.public_state()["point"], "source_frame": planning["source_frame"],
                                   "status": "rejected", "earliest_contact": planning["earliest_contact"]}
                    planning = None
            if scheduled is not None and scheduled["prepared"]["k_effect"] <= frame:
                candidate = scheduled.get("candidate")
                if candidate is not None:
                    candidate["plan"].update(scheduled["prepared"]["delivery"])
                    scheduled["selection"] = {**candidate["plan"]["selection"],
                        **{k: candidate["plan"][k] for k in ("goal_status", "predicted_landing",
                           "target_error_m", "net_clearance_m", "delivery")}}
                    if "replaces_contact" in candidate["plan"]:
                        event("replacement_validated", source_frame=scheduled["source_frame"])
                low, feedback = env._layer.lower("A", scheduled["command"], scheduled["prepared"], env.match)
                applied = env.match.apply("A", low)
                entry = {"source_frame": scheduled["source_frame"], "action": low, "action_result": {**feedback, **applied},
                         "command": scheduled["command"], "selection": scheduled["selection"], "intent_id": scheduled["intent_id"]}
                invalid += int("rejected" in applied)
                if entry["selection"] is not None and entry["selection"]["kind"] == "rally" and "rejected" not in applied:
                    origin = next((d for d in deliveries if d["id"] == entry["intent_id"]), None)
                    if origin is not None:
                        entry["intent_to_racket_plan_seconds"] = ((frame - origin["accepted_frame"]) * period
                            if mode == "simulated" else now - origin["accepted_monotonic"])
                        intention_delays.append(entry["intent_to_racket_plan_seconds"])
                history.append({"frame": frame, "command": entry["command"], "action_result": entry["action_result"]})
                event("executed", **entry)
                if candidate is not None:
                    ack = {"point": env.public_state()["point"], "source_frame": scheduled["source_frame"],
                           "status": "installed" if "rejected" not in applied else "rejected",
                           "plan": candidate["plan"], "earliest_contact": candidate["plan"]["t"]}
                scheduled = None
            if control is not None and control.done() and (mode == "realtime" or frame >= control.ready_frame):
                ready_control = control.result()
                control = None
            if ready_control is not None:
                row, ready_control = ready_control, None
                snapshot = row["snapshot"]
                compute_values.append(row["local_compute_seconds"])
                event("observation", **snapshot, local_compute_seconds=row["local_compute_seconds"])
                event("feedback_check", source_frame=snapshot["frame"], feedback=row["feedback"])
                state = env.public_state()
                same_point = snapshot["state"]["point"] == state["point"]
                command = row["command"]
                if command is not None:
                    if same_point:
                        commands.append({"command": command, "source_frame": snapshot["frame"],
                            "selection": row["selection"],
                            "intent_id": None if row["selection"] is None else row["selection"]["intent_id"],
                            "generation": generation, "candidates": row["candidates"]})
                        event("command_queued", source_frame=snapshot["frame"], selection=row["selection"])
                    else:
                        event("command_discarded", source_frame=snapshot["frame"], reason="previous_point")
                refresh = intent is None or intent_source_frame / 100 + intent["horizon_game_s"] - frame / 100 <= (
                    profile["summary"]["p95"] / 1000 / config["slowdown"])
                if (not preflight and source != "rules" and same_point and request is None
                        and refresh and frame >= next_request):
                    if calls >= config["max_calls"]:
                        reason = "request_limit"
                        break
                    request_info = {"id": calls, "generation": generation, "point": state["point"],
                                    "source_frame": snapshot["frame"],
                                    "capture_monotonic": row["capture_monotonic"]}
                    directory = output / "requests" / f"request-{calls:05d}"
                    # Bind source identity before the next request can replace request_info.
                    def publish(response, origin=request_info):
                        published.put((origin, response))
                    if mode == "simulated":
                        delay, service = _sample_delays(profile, rng)
                        request_info.update(ready_frame=frame + math.ceil(delay / period),
                                            release_frame=frame + math.ceil(service / period),
                                            delay_seconds=delay, service_seconds=service, published=False)
                        request = api_pool.submit(subscribe, snapshot, directory)
                    else:
                        request = api_pool.submit(api.act, realtime_prompt(snapshot),
                            Path(snapshot["images"][-1]["path"]).read_bytes(), spec, directory, publish)
                    event("request_issued", **request_info)
                    calls += 1
                    next_request = frame + config["request_stride"]
            if commands and planning is None and scheduled is None:
                item = commands.popleft()
                candidates = item["candidates"] or [{"command": item["command"], "plan": None}]
                items = []
                issued = time.monotonic()
                for index, candidate in enumerate(candidates):
                    try:
                        # Waiting consumes preparation; the absolute contact never moves.
                        command = native_action(candidate["command"], frame + lead)
                        cmd = parse_action(env._layer, "A", command, env.match, {})
                    except (ValueError, Refused) as exc:
                        event("command_rejected", reason=str(exc), source_frame=item["source_frame"], candidate=index)
                        continue
                    job = env._layer.snapshot("A", cmd, env.match, frame)
                    if job.get("none"):
                        scheduled = {**item, "command": cmd, "prepared": env._layer.prepare(job)}
                    else:
                        items.append({"index": index, "command": cmd, "candidate": candidate if candidate["plan"] else None,
                                      "future": plan_pool.submit(_plan, job, candidate if candidate["plan"] else None)})
                if items:
                    planning = {**item, "items": items, "frame": frame, "monotonic": issued,
                                "effect_frame": frame + lead,
                                "earliest_contact": min(c["command"]["contact_at_game_time"] for c in candidates)}
                    if mode == "simulated":
                        for planned in items:
                            planned["future"].result()
                elif item["candidates"]:
                    ack = {"point": env.public_state()["point"], "source_frame": item["source_frame"],
                           "status": "rejected", "earliest_contact": candidates[0]["plan"]["t"]}
            if frame > 0 and frame % config["observation_stride"] == 0 and control is None:
                control = capture()
            result = env.step(Action(None, "noop", True))
            frame += 1
            metrics = result.info["task_metrics"]
            if result.info.get("soft_reset"):
                event("soft_reset")
                generation += 1
                intent = intent_id = intent_source_frame = scheduled = ack = None
                next_request = frame
                while commands:
                    event("command_discarded", source_frame=commands.popleft()["source_frame"], reason="previous_point")
            if frame % 100 == 0:
                event("clock", elapsed_wall_seconds=time.monotonic() - started, lag_seconds=lag)
                _write(output / "progress.json", {"status": "running", "frame": frame, "game_seconds": frame / 100,
                       "wall_seconds": time.monotonic() - started, "calls": calls, "accepted": accepted, **metrics})
            if checkpoint is not None and len(env.match.g.results) > initial_results:
                status, reason = "diagnostic_completed", "leg_verdict"
                break
            if result.done:
                status, reason = "completed", "native_terminal"
                break
        else:
            status, reason = ("preflight_completed", "preflight_window") if preflight else ("incomplete", "game_time_limit")
        if started is not None:
            remaining = started + (frame - first_frame) * period - time.monotonic()
            if mode == "realtime" and remaining > 0:
                time.sleep(remaining)
            elapsed = time.monotonic() - started
    except BudgetError:
        status, reason = "incomplete", "budget_limit"
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
        _write(output / "failure.json", error)
        raise
    finally:
        try:
            if request is not None:
                final_response = request.result()
                if mode == "realtime":
                    results.append(final_response)
        except BaseException as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            _write(output / "failure.json", error)
        api_pool.shutdown(wait=True)
        if subscription is not None:
            subscription.close()
        control_pool.shutdown(wait=True, cancel_futures=True)
        plan_pool.shutdown(wait=True, cancel_futures=True)
        clock = timing_stats(lag_values)
        clock_valid = bool(lag_values and clock["p99"] <= config["lag_p99_limit_seconds"]
                           and clock["max"] <= config["lag_max_limit_seconds"])
        accounting = {"committed_usd": "0", "requests": {}, "blocked": None} if api is None else api.ledger.snapshot()
        episode_requests = {} if api is None else {rid: accounting["requests"][rid] for rid in api.request_ids}
        terminal_complete = accounting["blocked"] is None and all(r["status"] == "settled" for r in episode_requests.values())
        actual_cost = sum((Decimal(r["actual_usd"]) for r in episode_requests.values()
                           if r["status"] == "settled"), Decimal(0))
        if api is not None and config["ledger_path"] is not None:
            _write(output / "ledger.json", accounting)
        complete = status == "completed" and clock_valid and terminal_complete and error is None
        summary = {"mode": ("subscription_with_simulated_profile" if mode == "simulated" else
                             "realtime_fixed" if source == "rules" else
                             "realtime_api_preflight" if preflight else "realtime_api"), "status": status,
                   "slowdown": config["slowdown"],
                   "stop_reason": reason, "complete": complete, "native_match_completed": status == "completed",
                   "won": metrics["success"] if complete else None, "points_for": metrics["points_for"],
                   "points_against": metrics["points_against"], "seed": config["seed"], "frames": frame,
                   "game_seconds": (frame - first_frame) / 100, "wall_seconds": elapsed, "calls": calls, "accepted": accepted,
                   "invalid": invalid, "late_plans": late_plans, "discarded_previous_point": discarded,
                   "late_candidates": late_candidates,
                   "discarded_expired": expired,
                   "queued_commands_at_end": len(commands),
                   "cost_usd": str(actual_cost), "committed_usd": accounting["committed_usd"],
                   "actual_api_calls": len(episode_requests), "terminal_accounting_complete": terminal_complete,
                   "clock_valid": clock_valid, "clock_lag_seconds": clock,
                   "local_compute_seconds": timing_stats(compute_values),
                   "capture_to_accept_seconds": timing_stats([d["capture_to_accept_seconds"] for d in deliveries]),
                   "intent_to_racket_plan_seconds": timing_stats(intention_delays),
                   "api_json_ready_seconds": timing_stats([r["timing"]["json_ready_seconds"] for r in results]),
                   "api_terminal_seconds": timing_stats([r["timing"]["terminal_seconds"] for r in results]),
                   "error": error, "planning_lead_steps": lead, "first_frame": first_frame,
                   "native_planning_time_injected": True, "source": source,
                   "diagnostic_outcome": env.match.g.results[-1] if checkpoint is not None
                       and len(env.match.g.results) > initial_results else None}
        _write(output / "summary.json", summary)
        _write(output / "profile.json", {"source": "subscription_simulation" if mode == "simulated" else "actual_realtime_gameplay",
               "artificial_delay": mode == "simulated",
               "samples": results, "sample_count": len(results), "capture_to_accept_seconds": summary["capture_to_accept_seconds"],
               "json_ready_seconds": summary["api_json_ready_seconds"], "terminal_seconds": summary["api_terminal_seconds"],
               "cost_usd": str(actual_cost), "terminal_accounting_complete": terminal_complete})
        _write(output / "progress.json", summary)
        event("summary", **summary)
        log.close()
        if api is not None:
            api.close()
        env.close()
        for s, handler in handlers.items():
            signal.signal(s, handler)
    if error is not None:
        raise RuntimeError(f'Realtime request failed: {error["type"]}')
    return summary
