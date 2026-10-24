"""One serial visual placement loop shared by profile simulation, real-time evaluation, rules baselines and replay.

The loop is Asterix's: the screen is captured at fixed observation ticks into a rolling window; one request is in
flight; a new request is captured at the first tick after the previous reply arrived and its keys were pressed, with
the window's oldest, middle and newest images and their frame numbers; the reply is applied when it arrives
(sampled delay in simulation, actual arrival in real time); ticks while a request is in flight are counted as drops.
The actor sees only those images, the frame numbers and its own applied placements.
"""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import math
from pathlib import Path
import random
import statistics
import time

from baseline import RulesActor, features
from engine import NOOP, Tetris
from executor import KeyExecutor, key_script, parse_answer
from render import render
from task import build_task, profile_delays, request_text

FPS = 60
SCALE = 2  # screenshots are upscaled 2x (nearest) before they are sent; hashes are of the PNG bytes


def png(screen) -> bytes:
    from PIL import Image
    image = Image.fromarray(screen)
    image = image.resize((image.width * SCALE, image.height * SCALE), Image.Resampling.NEAREST)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def delay_frames(seconds: float, slowdown: float = 1.0) -> int:
    """Wall-clock seconds become game frames; a slowed game makes the same delay cover fewer frames."""
    if not math.isfinite(seconds) or seconds <= 0 or not math.isfinite(slowdown) or slowdown < 1:
        raise ValueError("Positive latency and finite slowdown >= 1 required")
    return max(1, math.ceil(seconds / slowdown * FPS))


def select_images(window):
    """Asterix's selection: oldest, third-newest and newest frames of the window."""
    n = len(window)
    return [window[i] for i in sorted({0, max(0, n - 3), n - 1})]


def make_env(seed: int, level: int, prefix: int) -> Tetris:
    """A deterministic start state: ``prefix`` pieces placed by the rules baseline at zero delay."""
    env = Tetris(seed=seed, start_level=level)
    rules = RulesActor()
    for _ in range(prefix):
        if env.over:
            break
        answer = {**json.loads(rules.act_on_truth(env)[0]), "piece": env.kind}
        for key in key_script(answer):  # press, release
            env.step(key)
            env.step(NOOP)
    return env


def board_state(env: Tetris) -> dict:
    height, _, holes, bump = features(env.board)
    return {"lines": env.lines, "pieces": env.pieces, "score": env.score, "level": env.level,
            "holes": holes, "height_sum": height, "bumpiness": bump}


def run_episode(root, recipe, out: Path, case: dict, task: str, delays: list[float], client, mode: str, provider: str,
                duration: float, slowdown: float):
    out.mkdir(parents=True, exist_ok=False)
    args = recipe["args"]
    stride, window = int(args["observation_stride_frames"]), deque(maxlen=int(args["observation_window"]))
    env = make_env(case["seed"], case["level"], case.get("prefix", 0))
    start = board_state(env)
    rng = random.Random(int(args.get("latency_seed_offset", 0)) + case.get("delay_seed", case["seed"]))
    executor, requests, deliveries, pending = KeyExecutor(), [], [], None
    horizon = round(duration * FPS)
    frame, drops, lag_max, started = 0, 0, 0.0, time.monotonic()
    pool = ThreadPoolExecutor(1)
    status, error = "horizon", None

    def request(text, images, directory):
        answer, meta = client.act(text, images, directory)
        return {"answer": answer, "meta": meta}

    try:
        with (out / "steps.jsonl").open("w") as steps, (out / "issued.jsonl").open("w") as issued:
            while frame < horizon and not env.over:
                if mode == "realtime":
                    remaining = started + frame * slowdown / FPS - time.monotonic()
                    if remaining > 0:
                        time.sleep(remaining)
                    lag_max = max(lag_max, time.monotonic() - started - frame * slowdown / FPS)
                screen = render(env)
                executor.observe(screen)
                if pending is not None:
                    row, future = pending
                    available = frame >= row["action_ready_frame"] if mode == "simulation" else future.done()
                    if available:
                        result = future.result()
                        row["delivery_frame"] = frame
                        row.update(answer=result["answer"], call_wall_seconds=result["meta"].get("wall_seconds"),
                                   output_tokens=result["meta"].get("output_tokens"))
                        try:
                            answer = parse_answer(result["answer"])
                            row["status"] = executor.apply(answer, row["target"], frame)
                        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                            row.update(status="invalid", error=str(exc)[:200])
                        deliveries.append({"frame": frame, "seq": row["seq"], "mode": mode, "status": row["status"],
                                           "capture_to_apply_s": (frame - row["obs_frame"]) / FPS,
                                           "actual_capture_to_apply_s": time.monotonic() - started - row["capture_wall_seconds"]})
                        pending = None
                if frame % stride == 0:
                    window.append((frame, png(screen)))
                    if pending is not None or executor.busy:
                        drops += 1  # a tick while a request is in flight or its keys are still being pressed
                    else:
                        images = select_images(window)
                        text = request_text(task, frame, [f for f, _ in images], executor.applied)
                        sampled = rng.choice(delays) if mode == "simulation" else None
                        row = {"seq": len(requests), "obs_frame": frame, "target": executor.piece_index,
                               "image_frames": [f for f, _ in images], "image_sha256": [hashlib.sha256(im).hexdigest() for _, im in images],
                               "sampled_capture_to_complete_s": sampled, "capture_wall_seconds": time.monotonic() - started,
                               "action_ready_frame": frame + delay_frames(sampled, slowdown) if sampled is not None else None,
                               "delivery_frame": None}
                        issued.write(json.dumps(row) + "\n"); issued.flush()
                        call_dir = out / "calls" / f"call-{row['seq']:05d}"
                        if provider == "rules":
                            answer_text, meta = client.act_on_truth(env)
                            call_dir.mkdir(parents=True)
                            (call_dir / "result.json").write_text(json.dumps({"answer": answer_text, "meta": meta}))
                            future = pool.submit(lambda a=answer_text, m=meta: {"answer": a, "meta": m})
                        elif mode == "simulation":
                            result = request(text, [im for _, im in images], call_dir)  # virtual clock waits for computation
                            future = pool.submit(lambda r=result: r)
                        else:
                            future = pool.submit(request, text, [im for _, im in images], call_dir)
                        requests.append(row)
                        pending = (row, future)
                action = executor.action(env.prev_action)
                env.step(action)
                steps.write(json.dumps({"frame": frame, "action": action, "lines": env.lines, "pieces": env.pieces}) + "\n")
                frame += 1
                if frame % 60 == 0:
                    steps.flush()
                    (out / "progress.json").write_text(json.dumps({"frames": frame, "game_seconds": frame / FPS, "lines": env.lines - start["lines"],
                                                                   "pieces": env.pieces - start["pieces"], "calls": len(requests), "drops": drops, "mode": mode}) + "\n")
                if env.over:
                    status = "natural_end"
    except BaseException as exc:
        error, status = {"type": type(exc).__name__, "message": str(exc)[:500]}, "interrupted"
        raise
    finally:
        pool.shutdown(wait=True)
        with (out / "decisions.jsonl").open("w") as log:
            for row in requests:
                if row["delivery_frame"] is None:
                    row["status"] = row.get("status", "unapplied_after_horizon")
                log.write(json.dumps(row) + "\n")
        (out / "actions.json").write_text(json.dumps(executor.applied, indent=1) + "\n")
        (out / "deliveries.json").write_text(json.dumps(deliveries, indent=1) + "\n")
        end = board_state(env)
        ages = sorted(d["capture_to_apply_s"] for d in deliveries)
        elapsed = time.monotonic() - started
        summary = {"case": case, "mode": mode, "provider": provider, "slowdown": slowdown,
                   "frames": frame, "game_seconds": frame / FPS, "environment_wall_seconds": elapsed, "virtual_wall_seconds": frame * slowdown / FPS,
                   "start": start, "end": end, "lines": end["lines"] - start["lines"], "pieces": end["pieces"] - start["pieces"],
                   "new_holes": end["holes"] - start["holes"], "height_delta": end["height_sum"] - start["height_sum"],
                   "survived": not env.over, "calls": len(requests), "drops": drops, "peak_inflight": int(bool(requests)),
                   "applied": sum(r.get("status") == "applied" for r in requests),
                   "stale": sum(r.get("status") == "stale" for r in requests), "invalid": sum(r.get("status") == "invalid" for r in requests),
                   "capture_to_apply_game_s_median": statistics.median(ages) if ages else None,
                   "capture_to_apply_game_s_max": max(ages) if ages else None,
                   "max_frame_lag_seconds": lag_max if mode == "realtime" else None, "status": status, "error": error,
                   "limitation": ("Sampled measured delays; actor computation pauses the virtual clock." if mode == "simulation"
                                  else "Actual response latency on a continuously advancing clock.")}
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def episodes_from(recipe: dict, args) -> list[dict]:
    if args.seed is not None:
        return [{"seed": args.seed, "level": args.level or 1, "prefix": args.prefix or 0}]
    return list(recipe["args"]["episodes"])


def run_recipe(root, recipe, out: Path, args, client_factory, mode: str, provider: str):
    duration = args.duration if args.duration is not None else recipe["args"]["duration"]
    slowdown = args.slowdown if args.slowdown is not None else float(recipe["args"].get("slowdown", 1))
    if slowdown != float(recipe["args"].get("slowdown", 1)):
        recipe = {**recipe, "args": {**recipe["args"], "slowdown": slowdown}}  # the task text states the run's slowdown
    system, task = build_task(root, recipe, mode)
    delays = profile_delays(root, recipe)
    (out / "task.txt").write_text(task)
    client = client_factory(output=out / "transport-worker", system=system)
    summaries = []
    try:
        for i, case in enumerate(episodes_from(recipe, args)):
            name = f"episode-{i:02d}-s{case['seed']}-l{case['level']}-p{case.get('prefix', 0)}"
            try:
                summaries.append(run_episode(root, recipe, out / name, case, task, delays, client, mode, provider, duration, slowdown))
            except BaseException:
                partial = out / name / "summary.json"
                if partial.exists():
                    summaries.append(json.loads(partial.read_text()))
                raise
    finally:
        client.close()
        n = len(summaries)
        mean = lambda key: (sum(s[key] for s in summaries) / n) if n else None  # noqa: E731
        ages = sorted(a for s in summaries for a in [s.get("capture_to_apply_game_s_median")] if a is not None)
        aggregate = {"episodes": n, "lines_mean": mean("lines"), "new_holes_mean": mean("new_holes"),
                     "height_delta_mean": mean("height_delta"), "pieces_mean": mean("pieces"),
                     "survived": sum(s["survived"] for s in summaries), "calls": sum(s["calls"] for s in summaries),
                     "drops": sum(s["drops"] for s in summaries), "stale": sum(s["stale"] for s in summaries),
                     "invalid": sum(s["invalid"] for s in summaries),
                     "capture_to_apply_game_s_median_of_medians": statistics.median(ages) if ages else None}
        (out / "summary.json").write_text(json.dumps({
            "mode": mode, "provider": provider, "clock": "virtual" if mode == "simulation" else "wall",
            "duration_game_seconds": duration, "slowdown": slowdown, "observation_stride_frames": recipe["args"]["observation_stride_frames"],
            "aggregate": aggregate, "episodes": summaries,
            "status": "interrupted" if any(s.get("status") == "interrupted" for s in summaries) else "completed",
            "limitation": ("Sampled measured delays; actor computation pauses the virtual clock." if mode == "simulation"
                           else "Actual response latency on a continuously advancing clock."),
        }, indent=2) + "\n")
    return summaries


def verify_replay(root, recipe, episode_dir: Path) -> dict:
    """Zero-model replay: rebuild the episode from its recorded answers and delivery frames; check every issued image hash
    and the final board. No model is called."""
    summary = json.loads((episode_dir / "summary.json").read_text())
    case = summary["case"]
    stride, window = int(recipe["args"]["observation_stride_frames"]), deque(maxlen=int(recipe["args"]["observation_window"]))
    requests = [json.loads(line) for line in (episode_dir / "decisions.jsonl").read_text().splitlines()]
    env, executor = make_env(case["seed"], case["level"], case.get("prefix", 0)), KeyExecutor()
    by_obs = {r["obs_frame"]: r for r in requests}
    by_delivery = {r["delivery_frame"]: r for r in requests if r.get("delivery_frame") is not None}
    checked = 0
    for frame in range(summary["frames"]):
        screen = render(env)
        executor.observe(screen)
        if frame in by_delivery:
            row = by_delivery[frame]
            if row["status"] != "invalid":
                status = executor.apply(parse_answer(row["answer"]), row["target"], frame)
                if status != row["status"]:
                    raise AssertionError(f"executor status mismatch at frame {frame}: {status} vs {row['status']}")
        if frame % stride == 0:
            window.append((frame, png(screen)))
            if frame in by_obs:
                images = select_images(window)
                hashes = [hashlib.sha256(im).hexdigest() for _, im in images]
                if hashes != by_obs[frame]["image_sha256"]:
                    raise AssertionError(f"image mismatch at frame {frame}")
                checked += 1
        env.step(executor.action(env.prev_action))
    end = board_state(env)
    if end != summary["end"] or (not env.over) != summary["survived"]:
        raise AssertionError("final board state does not match the recorded summary")
    if checked != len(requests):
        raise AssertionError("not every issued request was checked")
    return {"episode": episode_dir.name, "verified_frames": summary["frames"], "verified_requests": checked,
            "lines": summary["lines"], "survived": summary["survived"], "model_calls": 0}


def profile_inputs(root, recipe, episode_dir: Path, output: Path, client_factory, provider: str, max_calls: int) -> dict:
    """Strictly serial latency measurement: resend retained request inputs one at a time; no gameplay."""
    calls = sorted(p for p in (episode_dir / "calls").glob("call-*") if (p / "prompt.txt").exists() and (p / "image_0.png").exists())
    if not calls:
        raise ValueError("No retained request inputs (calls/*/prompt.txt + image_*.png) in " + str(episode_dir))
    system, _ = build_task(root, recipe, "realtime")
    client = client_factory(output=output.with_suffix("") / "transport", system=system)
    rows = []
    try:
        for call in calls[:max_calls]:
            text = (call / "prompt.txt").read_text()
            images = [p.read_bytes() for p in sorted(call.glob("image_*.png"))]
            started = time.monotonic()
            try:
                answer, meta = client.act(text, images, output.with_suffix("") / "transport" / call.name)
                wall = time.monotonic() - started
                parse_answer(answer)
                rows.append({"input": call.name, "wall_seconds": wall, "valid": True, "output_tokens": meta.get("output_tokens")})
            except Exception as exc:  # retained as an invalid sample, never used as a delay
                rows.append({"input": call.name, "wall_seconds": time.monotonic() - started, "valid": False, "error": type(exc).__name__})
    finally:
        client.close()
    valid = sorted(r["wall_seconds"] for r in rows if r["valid"])
    profile = {"capture_to_complete_seconds": valid, "provider": provider, "concurrency": 1,
               "source_episode": str(episode_dir), "attempted": len(rows), "valid_completed": len(valid),
               "median_s": statistics.median(valid) if valid else None, "rows": rows,
               "definition": "wall seconds from sending the retained prompt+images to receiving a complete, parseable answer"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, indent=1) + "\n")
    return {k: v for k, v in profile.items() if k != "rows"}
