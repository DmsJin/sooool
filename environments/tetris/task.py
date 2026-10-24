"""Build the exact text an actor receives: policy files, delay statement, mode sentence and public history."""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path


def profile_delays(root: Path, recipe: dict) -> list[float]:
    delays = json.loads((root / recipe["profile"]).read_text())["capture_to_complete_seconds"]
    if not delays or any((not isinstance(d, (int, float))) or not math.isfinite(d) or d <= 0 for d in delays):
        raise ValueError("Profile must list positive finite capture-to-complete seconds")
    return [float(d) for d in delays]


def quantile(values: list[float], q: float) -> float:
    values = sorted(values)
    position = (len(values) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def timing_sentence(delays: list[float], slowdown: float, mode: str) -> str:
    median, p95 = statistics.median(delays) / slowdown, quantile(delays, 0.95) / slowdown
    speed = "" if slowdown == 1 else f" The game runs {slowdown:g}x slower than normal speed."
    if mode == "simulation":
        return (f"Your answer takes effect about {median:.1f} seconds of GAME time after the screenshot was taken "
                f"(a delay sampled from a measured profile: median {median:.1f} s, 95th percentile {p95:.1f} s in game time).{speed} "
                "Your own computation time does not advance this simulated game.")
    return (f"Your answer takes effect when it actually arrives, typically {median:.1f} seconds of GAME time after the "
            f"screenshot was taken (previously measured delay: median {median:.1f} s, 95th percentile {p95:.1f} s in game time).{speed} "
            "The game keeps advancing while you compute.")


def read(root: Path, recipe: dict, key: str) -> str:
    return (root / recipe[key]).read_text().strip()


def build_task(root: Path, recipe: dict, mode: str, history: list[str] | None = None) -> tuple[str, str]:
    """Return (system, user_text) for one request. ``history`` is the public list of executed placements."""
    if mode not in ("simulation", "realtime"):
        raise ValueError(mode)
    slowdown = float(recipe["args"].get("slowdown", 1))
    timing = timing_sentence(profile_delays(root, recipe), slowdown, mode)
    prompt = read(root, recipe, "prompt").replace("{timing}", timing)
    executed = "\n".join(history[-4:]) if history else "(nothing executed yet)"
    text = "\n\n".join([
        read(root, recipe, "task_prefix"),
        prompt,
        "## Policy memory (notes kept from earlier practice)\n" + read(root, recipe, "memory"),
        "## What the game has already executed (oldest first)\n" + executed,
        "## Output\n" + read(root, recipe, "output_instructions"),
    ]) + "\n"
    return read(root, recipe, "system"), text
