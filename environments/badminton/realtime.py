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

from .api import TacticalAPI, realtime_prompt
from .public import native_action, public_data, public_spec
from .runner import _write
from .tactics import TacticalPlayer

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
    if intent is not None and intent_id != _player.intent_id:
        _player.accept(intent, intent_id, source_game_time=intent_source_frame / 100)
    command = _player.act({"state": state, "observation": {"image_png_b64": base64.b64encode(png).decode(), **metadata}})
    if command is not None and command["type"] == "act":
        command = dict(command)
        # Goal commands already name the absolute contact relative to this observation.
        # Native reference serving commands name preparation after the mechanical lead.
        lead = 0 if _player.selection is not None and _player.selection["kind"] == "rally" else _player.reference.lead
        command["contact_at_game_time"] = (state["step"] + lead + round(command.pop("t") * 100)) / 100
    snapshot = {"frame": state["step"], "game_time": state["step"] / 100,
                "state": public_data(state), "spec": public_spec(_control.spec),
                "camera_metadata": public_data(metadata), "images": [{"path": str(image), "frame": state["step"]}],
                "intent": _player.intent, "intent_id": _player.intent_id,
                "memory": memory, "action_history": history, "feedback": _player.feedback,
                "latency": {"slowdown": _control.slowdown, "capacity": 1, "clock": "actual_realtime_api",
                            "profile_summary": profile["summary"]}}
    return {"snapshot": snapshot, "command": command, "selection": _player.selection,
            "feedback": _player.feedback,
            "capture_monotonic": captured,
            "local_compute_seconds": time.monotonic() - start}


def _start_planner():
    from .native import load_sport
    global _planner
    _planner = load_sport().worker_init("plan", "A", None)


def _plan(job):
    return _planner.plan(job)


def _warm_planner():
    return True


def timing_stats(values):
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None, "max": None}
    ordered = sorted(values)
    return {"count": len(values), "mean": statistics.fmean(values), "p50": statistics.median(values),
            "p95": ordered[math.ceil(len(values) * .95) - 1],
            "p99": ordered[math.ceil(len(values) * .99) - 1], "max": ordered[-1]}


def run_realtime(config, recipe, profile, output, *, key, budget_usd, preflight=False):
    """Record one actual-clock episode; only preflight can omit API generation."""
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
    spec = env._spec
    lead = spec["act"]["lead_steps"]
    _write(output / "run.json", {"config": config, "recipe": recipe, "seed": config["seed"],
                                "profile": profile, "preflight": preflight, "window_steps": frames})
    context = multiprocessing.get_context("spawn")
    control_pool = ProcessPoolExecutor(1, mp_context=context, initializer=_start_control, initargs=(spec, env._cfg))
    plan_pool = ProcessPoolExecutor(1, mp_context=context, initializer=_start_planner)
    api_pool = ThreadPoolExecutor(1, thread_name_prefix="badminton-api")
    api = None if preflight else TacticalAPI(key, output, budget_usd, recipe)
    stopped = threading.Event()
    handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    for s in handlers:
        signal.signal(s, lambda *_: stopped.set())
    published = queue.SimpleQueue()
    control = planning = scheduled = request = None
    commands = deque()
    intent = intent_id = intent_source_frame = None
    memory, history = "", []
    generation = calls = accepted = invalid = late_plans = discarded = expired = 0
    next_request, request_info = 0, None
    lag_values, deliveries, compute_values, results, intention_delays = [], [], [], [], []
    log = (output / "events.jsonl").open("w", buffering=1)
    status, reason, error = "interrupted", None, None
    frame, started, elapsed = 0, None, 0.0
    metrics = {"points_for": 0, "points_against": 0, "success": False}

    def event(kind, **fields):
        log.write(json.dumps({"event": kind, "frame": frame, **fields}, separators=(",", ":"), allow_nan=False) + "\n")

    def capture():
        captured = time.monotonic()
        job, metadata = env.match.camera_job("A")
        current = env.public_state()
        current["pending_commands"] = bool(commands) or planning is not None or scheduled is not None
        return control_pool.submit(_control, job, current, metadata, intent, intent_id, intent_source_frame,
                                   memory, history[-16:], profile, str(output), captured)

    try:
        # Warm both native workers before starting the measured game clock.
        plan_pool.submit(_warm_planner).result()
        initial = capture().result()
        started = time.monotonic()
        event("reset", state=state, planning_lead_steps=lead)
        control = None
        ready_control = initial
        while frame < frames:
            due = started + frame * period
            remaining = due - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            now = time.monotonic()
            elapsed = now - started
            lag = max(0.0, now - due)
            lag_values.append(lag)
            if stopped.is_set() or Path(config["stop_file"]).exists():
                reason = "stop_requested"
                break
            if elapsed >= config["max_wall_seconds"]:
                reason = "wall_limit"
                break
            if lag > config["lag_max_limit_seconds"]:
                reason = "clock_lag_limit"
                break
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
                                "capture_to_accept_seconds": now - origin["capture_monotonic"],
                                "ready_to_accept_seconds": now - response["json_ready_monotonic"],
                                "accepted_monotonic": now, **response}
                    deliveries.append(delivery)
                    event("intent_accepted", **delivery)
            if request is not None and request.done():
                results.append(request.result())
                request = None
            if intent is not None and frame >= intent_source_frame + intent["horizon_game_s"] * 100:
                intent = intent_id = intent_source_frame = None
            if planning is not None and planning["future"].done():
                prepared = planning["future"].result()
                if planning["generation"] != generation or prepared["k_effect"] < frame:
                    late_plans += 1
                    event("planning_discarded", source_frame=planning["source_frame"],
                          effect_frame=prepared["k_effect"], reason="previous_point" if planning["generation"] != generation else "deadline")
                else:
                    scheduled = {**planning, "prepared": prepared}
                planning = None
            if scheduled is not None and scheduled["prepared"]["k_effect"] <= frame:
                low, feedback = env._layer.lower("A", scheduled["command"], scheduled["prepared"], env.match)
                applied = env.match.apply("A", low)
                entry = {"source_frame": scheduled["source_frame"], "action": low, "action_result": {**feedback, **applied},
                         "command": scheduled["command"], "selection": scheduled["selection"], "intent_id": scheduled["intent_id"]}
                invalid += int("rejected" in applied)
                if entry["selection"] is not None and entry["selection"]["kind"] == "rally" and "rejected" not in applied:
                    origin = next((d for d in deliveries if d["id"] == entry["intent_id"]), None)
                    if origin is not None:
                        entry["intent_to_racket_plan_seconds"] = now - origin["accepted_monotonic"]
                        intention_delays.append(entry["intent_to_racket_plan_seconds"])
                history.append({"frame": frame, "command": entry["command"], "action_result": entry["action_result"]})
                event("executed", **entry)
                scheduled = None
            if control is not None and control.done():
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
                            "generation": generation})
                        event("command_queued", source_frame=snapshot["frame"], selection=row["selection"])
                    else:
                        event("command_discarded", source_frame=snapshot["frame"], reason="previous_point")
                serving = state["you_serve"] and state["serve"]["phase"] != "done"
                if (not preflight and same_point and request is None and (state["ball_in_play"] or serving)
                        and frame >= next_request):
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
                    request = api_pool.submit(api.act, realtime_prompt(snapshot),
                        Path(snapshot["images"][-1]["path"]).read_bytes(), spec, directory, publish)
                    event("request_issued", **request_info)
                    calls += 1
                    next_request = frame + config["request_stride"]
            if commands and planning is None and scheduled is None:
                item = commands.popleft()
                try:
                    # Queue residence consumes preparation time, never shifts the contact.
                    command = native_action(item["command"], frame + lead)
                    cmd = parse_action(env._layer, "A", command, env.match, {})
                    job = env._layer.snapshot("A", cmd, env.match, frame)
                except (ValueError, Refused) as exc:
                    event("command_rejected", reason=str(exc), source_frame=item["source_frame"])
                else:
                    item["command"] = cmd
                    if job.get("none"):
                        scheduled = {**item, "prepared": env._layer.prepare(job)}
                    else:
                        planning = {**item, "future": plan_pool.submit(_plan, job)}
            if frame > 0 and frame % config["observation_stride"] == 0 and control is None:
                control = capture()
            result = env.step(Action(None, "noop", True))
            frame += 1
            metrics = result.info["task_metrics"]
            if result.info.get("soft_reset"):
                event("soft_reset")
                generation += 1
                intent = intent_id = intent_source_frame = scheduled = None
                while commands:
                    event("command_discarded", source_frame=commands.popleft()["source_frame"], reason="previous_point")
            if frame % 100 == 0:
                event("clock", elapsed_wall_seconds=time.monotonic() - started, lag_seconds=lag)
                _write(output / "progress.json", {"status": "running", "frame": frame, "game_seconds": frame / 100,
                       "wall_seconds": time.monotonic() - started, "calls": calls, "accepted": accepted, **metrics})
            if result.done:
                status, reason = "completed", "native_terminal"
                break
        else:
            status, reason = ("preflight_completed", "preflight_window") if preflight else ("incomplete", "game_time_limit")
        if started is not None:
            remaining = started + frame * period - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            elapsed = time.monotonic() - started
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
        _write(output / "failure.json", error)
        raise
    finally:
        try:
            if request is not None:
                results.append(request.result())
        except BaseException as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            _write(output / "failure.json", error)
        api_pool.shutdown(wait=True)
        control_pool.shutdown(wait=True, cancel_futures=True)
        plan_pool.shutdown(wait=True, cancel_futures=True)
        clock = timing_stats(lag_values)
        clock_valid = bool(lag_values and clock["p99"] <= config["lag_p99_limit_seconds"]
                           and clock["max"] <= config["lag_max_limit_seconds"])
        accounting = {"committed_usd": "0", "requests": {}, "blocked": None} if api is None else api.ledger.snapshot()
        terminal_complete = accounting["blocked"] is None and all(r["status"] == "settled" for r in accounting["requests"].values())
        actual_cost = sum((Decimal(r["actual_usd"]) for r in accounting["requests"].values()
                           if r["status"] == "settled"), Decimal(0))
        complete = status == "completed" and clock_valid and terminal_complete and error is None
        summary = {"mode": "realtime_api_preflight" if preflight else "realtime_api", "status": status,
                   "slowdown": config["slowdown"],
                   "stop_reason": reason, "complete": complete, "native_match_completed": status == "completed",
                   "won": metrics["success"] if complete else None, "points_for": metrics["points_for"],
                   "points_against": metrics["points_against"], "seed": config["seed"], "frames": frame,
                   "game_seconds": frame / 100, "wall_seconds": elapsed, "calls": calls, "accepted": accepted,
                   "invalid": invalid, "late_plans": late_plans, "discarded_previous_point": discarded,
                   "discarded_expired": expired,
                   "queued_commands_at_end": len(commands),
                   "cost_usd": str(actual_cost), "committed_usd": accounting["committed_usd"],
                   "actual_api_calls": len(accounting["requests"]), "terminal_accounting_complete": terminal_complete,
                   "clock_valid": clock_valid, "clock_lag_seconds": clock,
                   "local_compute_seconds": timing_stats(compute_values),
                   "capture_to_accept_seconds": timing_stats([d["capture_to_accept_seconds"] for d in deliveries]),
                   "intent_to_racket_plan_seconds": timing_stats(intention_delays),
                   "api_json_ready_seconds": timing_stats([r["timing"]["json_ready_seconds"] for r in results]),
                   "api_terminal_seconds": timing_stats([r["timing"]["terminal_seconds"] for r in results]),
                   "error": error, "planning_lead_steps": lead}
        _write(output / "summary.json", summary)
        _write(output / "profile.json", {"source": "actual_realtime_api_gameplay", "artificial_delay": False,
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
