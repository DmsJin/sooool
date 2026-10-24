"""Summarise registered Tetris runs into one Markdown table (no model calls).

    uv run python scripts/tetris_results.py RUN_DIR [RUN_DIR ...]
"""
import json
from pathlib import Path
import sys


def row(run: Path) -> str:
    summary = json.loads((run / "summary.json").read_text())
    manifest = json.loads((run / "manifest.json").read_text())
    agg = summary["aggregate"]
    by_level = {}
    for episode in summary["episodes"]:
        by_level.setdefault(episode["case"]["level"], []).append(episode)
    deaths = ", ".join(f"L{level}: {sum(not e['survived'] for e in eps)}" for level, eps in sorted(by_level.items())
                       if any(not e["survived"] for e in eps)) or "none"
    delay = agg.get("capture_to_apply_game_s_median_of_medians")
    return (f"| {run.name} | {manifest['provider']} | {manifest['clock']} | {summary['slowdown']:g}× | "
            f"{agg['episodes']} | {agg['lines_mean']:.2f} | {agg['new_holes_mean']:.2f} | {agg['height_delta_mean']:.1f} | "
            f"{agg['survived']}/{agg['episodes']} ({deaths}) | {agg['stale']} / {agg['invalid']} | "
            f"{'' if delay is None else f'{delay:.1f}'} |")


def main(paths):
    print("| Run | Provider | Clock | Slowdown | Episodes | Lines | New holes | Height Δ | Alive (deaths by start level) | Stale / invalid | Capture→apply (game s) |")
    print("|---|---|---|---|---:|---:|---:|---:|---|---|---:|")
    for path in paths:
        print(row(Path(path)))


if __name__ == "__main__":
    main(sys.argv[1:])
