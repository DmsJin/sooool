"""Counterfactual receptions from verified native prefixes, with camera-only control."""
import json
from pathlib import Path
import sys

from .realtime import run_realtime
from .realtime_report import _replay
from .runner import _write


def diagnose_receptions(source, output):
    """Replay each original incoming flight with its frozen public tactical goal."""
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    audit = json.loads((source / "audit.json").read_text())
    run = json.loads((source / "run.json").read_text())
    cases = {tuple(s["initial"]["stroke_id"]): s for s in audit["goal_strokes"]
             if s["outcome"] is not None}
    if not cases:
        raise ValueError("Reception diagnosis requires settled audited strokes")
    checkpoints = []
    seen = set()
    for env, frame, events, _ in _replay(source):
        for event in events:
            if event["event"] != "observation":
                continue
            state = event["state"]
            if state["ball_state"] != "coming to you":
                continue
            key = (state["point"], round(frame / 100 - state["t_since_played"], 3))
            if key in cases and key not in seen:
                seen.add(key)
                choice = cases[key]["initial"]["requested_choice"]
                intent = {**{branch: choice for branch in ("normal", "under_pressure", "opponent_back")},
                          "recovery": [0, -1.6], "horizon_game_s": 10, "memory": "Frozen diagnostic goal."}
                wc = sys.modules["wc"]
                checkpoints.append((key, {"native": wc.snapshot(env.match.g), "intent": intent}))
    rows = []
    for key, checkpoint in checkpoints:
        config = {**run["config"], "stop_file": str(output / "STOP")}
        result = run_realtime(config, run["recipe"], run["profile"], output / f"point-{key[0]}-at-{key[1]}",
                              key=None, budget_usd=None, preflight=True, source="rules",
                              mode="simulated", checkpoint=checkpoint)
        rows.append({"stroke_id": list(key), "before": cases[key]["outcome"],
                     "after": result["diagnostic_outcome"], "clock_valid": result["clock_valid"],
                     "invalid": result["invalid"], "late_plans": result["late_plans"]})
        _write(output / "progress.json", {"cases": rows})
    preserved = sum(r["before"]["returned"] and r["after"] is not None and r["after"]["returned"] for r in rows)
    legal = sum(r["after"] is not None and r["after"]["returned"] for r in rows)
    result = {"mode": "offline_counterfactual_frozen_goals", "source": str(source), "cases": rows,
              "model_calls": 0, "legal_returns": legal, "incoming": len(rows),
              "preserved_legal_returns": preserved,
              "complete": len(rows) == len(cases) and all(
                  r["after"] is not None and r["clock_valid"] and not r["invalid"] for r in rows)}
    _write(output / "comparison.json", result)
    return result
