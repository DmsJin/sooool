"""Conditional goals over S2 camera execution and independent native replay auditing."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import math
from pathlib import Path
import random
import signal
import statistics
import threading
import time

from runtime.subscription import SubscriptionClient
from . import public as badminton
from .tactics import POLICY_ROOT, SCHEMA, TacticalPlayer, decode_intent, format_prompt

PROFILE_CALLS = 20
PROFILE_SERVICE_TIER = "ultrafast"


def _environment(config, seed, frames):
    # Native MuJoCo is optional for the pure tactical tests.
    from .native import Action, BadmintonEnvironment
    return BadmintonEnvironment(level=config["level"], seed=seed, max_env_steps=frames + 1), Action


def _client(config, output):
    return SubscriptionClient(output=output, output_schema=SCHEMA,
                              system=(POLICY_ROOT / "system.txt").read_text(),
                              service_tier=config["subscription_service_tier"])


def _write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)



def _sample_delays(profile: dict, rng: random.Random) -> tuple[float, float]:
    sample = rng.choice(profile["samples"])
    if isinstance(sample, (int, float)):
        if profile.get("unit") not in {"ms", "seconds"}:
            raise ValueError("Scalar profile samples require unit=ms or seconds")
        ready = sample / 1000 if profile["unit"] == "ms" else sample
        service = ready
    else:
        ready = sample["latency_ms"] / 1000
        service = sample["service_ms"] / 1000
    if not (math.isfinite(ready) and math.isfinite(service) and 0 <= ready <= service):
        raise ValueError("Profile must satisfy 0 <= latency <= service, in wall time")
    return ready, service



def _quantiles(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {"count": len(values), "mean": statistics.fmean(values),
            "p95": ordered[math.ceil(len(values) * .95) - 1], "max": ordered[-1]}



def _snapshot(observation, image, player, memory, history, profile, slowdown, profile_info):
    snapshot = {
        "frame": observation.env_step, "game_time": observation.env_step / 100,
        "state": badminton.public_data(observation.data["state"]),
        "spec": badminton.public_spec(observation.metadata["spec"]),
        "camera_metadata": badminton.public_data({k: v for k, v in observation.data["observation"].items()
                                                  if k not in {"image_png_b64", "wall_mono"}}),
        "images": [{"path": str(image), "frame": observation.env_step}],
        "intent": player.intent, "intent_id": player.intent_id,
        "feedback": player.feedback,
        "memory": memory, "action_history": history[-16:],
        "latency": {"slowdown": slowdown, "capacity": 1},
    }
    if profile_info:
        snapshot["latency"]["profile_summary"] = profile.get("summary", {})
    return snapshot



def run_episode(config, source, seed, output, frames, profile=None, *, profile_info=True):
    """Run the same camera-only player with rule defaults or delayed online preferences.

    Local rendering, perception and shot selection incur measured game-time
    delay. Native mechanical planning is recorded, not injected, as in the
    existing simulated episode protocol. This is a development experiment.
    """
    profile = {} if profile is None else profile
    if source not in {"rules", "sol", "sol-frozen"}:
        raise ValueError("Tactical source must be rules, sol or sol-frozen")
    if config["slowdown"] <= 0 or config["level"] != 1:
        raise ValueError("This bounded round requires L1 and a positive slowdown")
    if source != "rules" and (profile.get("action_mode") != "conditional_tactical_v1" or profile.get("source") != "api"
                            or profile.get("service_tier") != PROFILE_SERVICE_TIER or not profile["usable_for_simulation"]
                            or len(profile["samples"]) != PROFILE_CALLS):
        raise ValueError("SOL requires the 20-call conditional API Ultrafast profile")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "images").mkdir()
    _write(output / "run.json", {"config": config, "strategy": {"action_mode": "tactical", "source": source,
                                                               "profile_info": profile_info},
                                "seed": seed, "profile": profile, "window_steps": frames})
    env, Action = _environment(config, seed, frames)
    stop = threading.Event()
    started = time.monotonic()
    frame = generation = calls = accepted = invalid = timing_errors = 0
    memory = ""
    history, render_costs, native_costs = [], [], []
    request, pending = None, None
    next_request = 0
    rng = random.Random(42 + seed)
    status, reason = "stopped", None
    last_info, last_state = {}, {}
    clients = ExitStack()
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tactical-sol")
    client = None
    log_file = (output / "events.jsonl").open("w", buffering=1)
    handlers = {}

    def log(event, **fields):
        log_file.write(json.dumps({"event": event, **fields}, separators=(",", ":"), allow_nan=False) + "\n")

    def stopped():
        return "signal" if stop.is_set() else "stop_file" if Path(config["stop_file"]).exists() else None

    def invoke(prompt, images, directory):
        reason = stopped()
        if reason is not None:
            return {"cancelled_before_start": reason}
        text, metadata = client.act(prompt, [Path(image).read_bytes() for image in images], directory)
        return {"text": text, "wall_seconds": metadata["wall_seconds"], "usage": metadata["token_usage"]}

    try:
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, lambda *_: stop.set())
        initial = env.reset(seed=seed)
        reference_class = env.sport.players()["reference"]
        player = TacticalPlayer(initial.metadata["spec"], reference_class)
        player.reset_point(initial.data["state"]["point"])
        last_state = badminton.public_data(initial.data["state"])
        log("reset", frame=0)
        while frame < frames:
            reason = stopped()
            if reason is not None:
                break
            if request is not None and frame >= request["ready_frame"] and not request["decided"]:
                response = request["future"].result()
                if "cancelled_before_start" in response:
                    reason = response["cancelled_before_start"]
                    break
                request["decided"] = True
                log("completion", id=request["id"], frame=frame, source_frame=request["source_frame"],
                    text=response["text"], wall_seconds=response["wall_seconds"], usage=response.get("usage"))
                if request["generation"] != generation:
                    log("discarded", id=request["id"], frame=frame, reason="previous_point")
                else:
                    try:
                        intent = decode_intent(response["text"], initial.metadata["spec"])
                    except ValueError as exc:
                        invalid += 1
                        log("discarded", id=request["id"], frame=frame, reason="invalid_output", error=str(exc))
                    else:
                        expires = request["source_frame"] / 100 + intent["horizon_game_s"]
                        if frame / 100 >= expires:
                            log("discarded", id=request["id"], frame=frame, reason="expired")
                        else:
                            player.accept(intent, request["id"], source_game_time=request["source_frame"] / 100)
                            memory = intent["memory"]
                            accepted += 1
                            log("intent_accepted", id=request["id"], frame=frame,
                                source_frame=request["source_frame"], intent=intent)
            if request is not None and request["decided"] and frame >= request["release_frame"]:
                request = None

            command = None
            execution = None
            if pending is not None and frame >= pending["ready_frame"]:
                ready, pending = pending, None
                if ready["generation"] != generation:
                    log("local_discarded", frame=frame, source_frame=ready["source_frame"], reason="previous_point")
                else:
                    command = ready["command"]
                    if command is not None:
                        try:
                            command = badminton.native_action(command, frame)
                        except ValueError as exc:
                            timing_errors += 1
                            log("timing_rejected", frame=frame, source_frame=ready["source_frame"], error=str(exc))
                            command = None
                        else:
                            execution = ready
                    snapshot = ready["snapshot"]
                    public_state = snapshot["state"]
                    serving = public_state["you_serve"] and public_state["serve"]["phase"] != "done"
                    if (source != "rules" and request is None and frame >= next_request
                            and (source != "sol-frozen" or player.intent is None)
                            and (public_state["ball_in_play"] or serving)):
                        if calls >= 64:
                            reason = "max_calls"
                            break
                        if client is None:
                            client = _client(config, output / "worker")
                            clients.callback(client.close)
                        directory = output / "requests" / f"request-{calls:05d}"
                        directory.mkdir(parents=True)
                        prompt = format_prompt(snapshot)
                        (directory / "prompt.txt").write_text(prompt)
                        _write(directory / "snapshot.json", snapshot)
                        latency, service = _sample_delays(profile, rng)
                        request = {"id": calls, "source_frame": snapshot["frame"], "generation": generation,
                                   "ready_frame": frame + math.ceil(latency * 100 / config["slowdown"]),
                                   "release_frame": frame + math.ceil(service * 100 / config["slowdown"]),
                                   "decided": False,
                                   "future": pool.submit(invoke, prompt, [snapshot["images"][-1]["path"]], directory)}
                        log("request_issued", id=calls, frame=frame, source_frame=snapshot["frame"],
                            generation=generation, ready_frame=request["ready_frame"],
                            release_frame=request["release_frame"])
                        calls += 1
                        next_request = frame + 100

            if pending is None and frame % 10 == 0:
                compute_started = time.perf_counter()
                observation = initial if frame == 0 else env.observe()
                last_state = badminton.public_data(observation.data["state"])
                image = output / "images" / f"frame-{frame:07d}.png"
                image.write_bytes(base64.b64decode(observation.data["observation"]["image_png_b64"]))
                selected = player.act(observation.data)
                if selected is not None and selected["type"] == "act":
                    selected = dict(selected)
                    selected["contact_at_game_time"] = (frame + round(selected.pop("t") * 100)) / 100
                snapshot = _snapshot(observation, image, player, memory, history, profile,
                                     config["slowdown"], profile_info)
                compute = time.perf_counter() - compute_started
                render_costs.append(compute)
                ready_frame = frame + math.ceil(compute * 100 / config["slowdown"])
                pending = {"source_frame": frame, "ready_frame": ready_frame, "generation": generation,
                           "command": selected, "snapshot": snapshot, "selection": player.selection}
                log("observation", **snapshot, local_ready_frame=ready_frame, local_compute_wall_seconds=compute)

            before = time.perf_counter()
            result = env.step(Action(None, name="noop", is_noop=True) if command is None else
                              Action(command, name=command["type"]))
            native_costs.append(time.perf_counter() - before)
            last_info = result.info
            if execution is not None:
                invalid += int(bool(result.info.get("invalid_action")))
                entry = {"id": len(history), "frame": frame, "source_frame": execution["source_frame"],
                         "action": command, "requested_action": execution["command"],
                         "selection": execution["selection"],
                         "action_result": badminton.public_data(result.info.get("action_result", {})),
                         "invalid_action": bool(result.info.get("invalid_action"))}
                history.append(entry)
                log("executed", **entry)
            frame += 1
            safe_info = {k: badminton.public_data(result.info[k]) for k in (
                "task_metrics", "soft_reset", "invalid_action", "action_error", "winner") if k in result.info}
            if execution is not None or result.reward or result.done or result.truncated or frame % 100 == 0:
                log("step", frame=frame, info=safe_info, done=result.done, truncated=result.truncated)
            if result.info.get("soft_reset"):
                generation += 1
                pending = None
                player.reset_point(None)
                log("soft_reset", frame=frame)
            if frame % 100 == 0:
                _write(output / "progress.json", {"status": "running", "frame": frame,
                       "calls": calls, "accepted": accepted, "invalid": invalid,
                       "task_metrics": result.info["task_metrics"]})
            if result.done:
                status, reason = "completed", "native_terminal"
                break
            if result.truncated:
                status, reason = "truncated", "native_truncated"
                break
        else:
            status, reason = "screen_completed", "screen_window_end"
    except BaseException as exc:
        status, reason = "failed", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        stop.set()
        pool.shutdown(wait=True, cancel_futures=True)
        clients.close()
        env.close()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        metrics = last_info.get("task_metrics", {})
        summary = {"status": status, "stop_reason": reason, "frames": frame, "game_seconds": frame / 100,
                   "seed": seed, "source": source, "profile_info": profile_info,
                   "action_mode": "tactical", "calls": calls,
                   "accepted": accepted, "invalid": invalid, "timing_rejections": timing_errors,
                   "points_for": metrics.get("points_for", 0), "points_against": metrics.get("points_against", 0),
                   "native_match_completed": status == "completed",
                   "won": metrics.get("success") if status == "completed" else None,
                   "wall_seconds": time.monotonic() - started, "last_observed_public_state": last_state,
                   "evidence_class": "fixed_window_development_screen",
                   "clock": {"mode": "simulated", "slowdown": config["slowdown"],
                             "local_compute_seconds": _quantiles(render_costs), "local_compute_injected": True,
                             "native_step_and_plan_seconds": _quantiles(native_costs),
                             "native_step_compute_injected": False}}
        _write(output / "summary.json", summary)
        _write(output / "progress.json", summary)
        log("summary", **summary)
        log_file.close()
    return summary



def audit_episode(directory):
    """Replay public execution evidence before reading diagnostic-only native results."""
    directory = Path(directory).resolve()
    run = json.loads((directory / "run.json").read_text())
    summary = json.loads((directory / "summary.json").read_text())
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    observations = {e["frame"]: e for e in events if e["event"] == "observation"}
    executions = {e["frame"]: e for e in events if e["event"] == "executed"}
    resets = {e["frame"] for e in events if e["event"] == "soft_reset"}
    env, Action = _environment(run["config"], run["seed"], run["window_steps"])
    mismatches = []
    trajectory = []
    try:
        env.reset(seed=run["seed"])
        for frame in range(summary["frames"]):
            trajectory.append({"frame": frame, "ball": [float(x) for x in env.match.g.s.sh_p],
                               "in_play": bool(env.match.g.in_play())})
            if frame in observations:
                state = badminton.public_data(env.public_state())
                if state != observations[frame]["state"]:
                    mismatches.append({"frame": frame, "kind": "public_state"})
            execution = executions.get(frame)
            command = None if execution is None else execution["action"]
            result = env.step(Action(None, name="noop", is_noop=True) if command is None else
                              Action(command, name=command["type"]))
            if execution is not None and badminton.public_data(result.info.get("action_result", {})) != execution["action_result"]:
                mismatches.append({"frame": frame, "kind": "native_feedback"})
            if bool(result.info.get("soft_reset")) != (frame + 1 in resets):
                mismatches.append({"frame": frame, "kind": "point_boundary"})
        metrics = result.info["task_metrics"]
        if any(metrics[k] != summary[k] for k in ("points_for", "points_against")):
            mismatches.append({"frame": summary["frames"], "kind": "score"})
        if result.done != summary["native_match_completed"]:
            mismatches.append({"frame": summary["frames"], "kind": "termination"})
        report = {"matched": not mismatches, "mismatches": mismatches, "model_calls": 0,
                  "purpose": "offline_audit_only_never_online_input"}
        if not mismatches:
            # Native result kinds are diagnostic evidence, unavailable to the player.
            results = [{k: r[k] for k in ("kind", "returned", "summary", "hit", "speed_out")} for r in env.match.g.results]
            serves = [r for r in results if r["kind"] == "our_serve"]
            incoming = [r for r in results if r["kind"] != "our_serve" and not (r["returned"] and not r["hit"])]
            report.update(results=results, trajectory=trajectory,
                          serves=len(serves), legal_serves=sum(r["returned"] for r in serves),
                          incoming=len(incoming), legal_returns=sum(r["returned"] for r in incoming),
                          opponent_faults=sum(r["kind"] != "our_serve" and r["returned"] and not r["hit"] for r in results),
                          unsettled_leg=env.match.g.leg["kind"] if not result.done else None)
        _write(directory / "audit.json", report)
        return report
    finally:
        env.close()
