"""Subscription simulation entrypoint and historical native replay auditing."""
from __future__ import annotations

import json
import math
from pathlib import Path
import random

from . import public as badminton

PROFILE_CALLS = 10
PROFILE_SERVICE_TIER = "ultrafast"


def _environment(config, seed, frames):
    # Native MuJoCo is optional for the pure tactical tests.
    from .native import Action, BadmintonEnvironment
    return BadmintonEnvironment(level=config["level"], seed=seed, max_env_steps=frames + 1), Action


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



def run_episode(config, source, seed, output, frames, profile=None):
    """Run subscription decisions through the shared native command scheduler."""
    from .realtime import run_realtime
    recipe = json.loads((Path(__file__).resolve().parents[2] / "recipes/badminton-realtime.json").read_text())
    if source != "rules" and (profile["source"] != "api" or profile["service_tier"] != PROFILE_SERVICE_TIER
                             or not profile["usable_for_simulation"]
                             or len(profile["samples"]) != profile["terminal_calls"]):
        raise ValueError("Simulation requires an explicitly counted API Ultrafast profile")
    resolved = {**recipe["args"], "seed": seed, "slowdown": config["slowdown"],
                "max_game_seconds": frames // 100, "stop_file": config["stop_file"]}
    return run_realtime(resolved, recipe, profile or {"summary": {"p95": 0}}, output,
                        key=None, budget_usd=None, source=source, mode="simulated")


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
