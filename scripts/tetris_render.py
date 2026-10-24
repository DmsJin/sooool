"""Render a recorded Tetris episode to a GIF by zero-model replay (deterministic replay rendering, not a screen capture).

    uv run python scripts/tetris_render.py RUN/episode-00-s0-l1-p20 out.gif [--fps 10]
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "environments/tetris")]

from PIL import Image, ImageDraw  # noqa: E402

from engine import NOOP  # noqa: E402
from executor import KeyExecutor, parse_answer  # noqa: E402
from render import render  # noqa: E402
from runner import FPS, make_env  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("episode", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--fps", type=int, default=10)
    a = p.parse_args()
    summary = json.loads((a.episode / "summary.json").read_text())
    case = summary["case"]
    requests = [json.loads(line) for line in (a.episode / "requests.jsonl").read_text().splitlines()]
    by_apply = {r["apply_frame"]: r for r in requests if "apply_frame" in r and r.get("status") in ("applied", "stale")}
    captures = {r["capture_frame"]: r for r in requests}
    env, executor = make_env(case["seed"], case["level"], case.get("prefix", 0)), KeyExecutor()
    lines0, frames, step = env.lines, [], max(1, FPS // a.fps)
    waiting, answers = None, 0
    for frame in range(summary["frames"]):
        screen = render(env)
        executor.observe(screen)
        if frame in captures:
            waiting = captures[frame]
        if frame in by_apply:
            row = by_apply[frame]
            executor.apply(parse_answer(row["answer"]), row["target"], frame)
            answers += 1
            waiting = None
        if frame % step == 0:
            image = Image.fromarray(screen)
            bar = Image.new("RGB", (image.width, 44), (24, 24, 34))
            d = ImageDraw.Draw(bar)
            d.text((6, 4), f"{summary['provider']}  {summary['mode']}  {summary['slowdown']:g}x  t={frame / FPS:4.1f}s  lines +{env.lines - lines0}  answers {answers}", fill=(230, 230, 240))
            d.text((6, 22), "waiting for answer (piece keeps falling)" if waiting else "executing / asking", fill=(255, 200, 120) if waiting else (140, 255, 160))
            canvas = Image.new("RGB", (image.width, image.height + 44))
            canvas.paste(bar, (0, 0))
            canvas.paste(image, (0, 44))
            frames.append(canvas)
        env.step(executor.action(env.prev_action) if not env.over else NOOP)
    frames[0].save(a.output, save_all=True, append_images=frames[1:], duration=int(1000 / a.fps), loop=0, optimize=True)
    print(f"{len(frames)} frames -> {a.output} ({a.output.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
