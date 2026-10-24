"""One serial visual placement loop shared by profile simulation, real-time evaluation, rules baselines and replay.

Protocol (declared in docs/tetris.md): one request in flight; a screenshot is captured when the piece in play has
no applied answer; the answer becomes a key script when it is delivered (sampled delay in simulation, actual arrival
in real time); the game keeps running meanwhile. The actor sees only the screenshot and its own applied history.
"""
from __future__ import annotations

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
from task import build_task, profile_delays

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


def make_env(seed: int, level: int, prefix: int) -> Tetris:
    """A deterministic start state: ``prefix`` pieces placed by the rules baseline at zero delay."""
    env = Tetris(seed=seed, start_level=level)
    rules = RulesActor()
    for _ in range(prefix):
        if env.over:
            break
        answer = json.loads(rules.act_on_truth(env)[0])
        for key in key_script(answer):  # press, release
            env.step(key)
            env.step(NOOP)
    return env


def board_state(env: Tetris) -> dict:
    height, _, holes, bump = features(env.board)
    return {"lines": env.lines, "pieces": env.pieces, "score": env.score, "level": env.level,
            "holes": holes, "height_sum": height, "bumpiness": bump}


def run_episode(root, recipe, out: Path, case: dict, client, mode: str, provider: str, duration: float, slowdown: float):
    out.mkdir(parents=True, exist_ok=False)
    env = make_env(case["seed"], case["level"], case.get("prefix", 0))
    start = board_state(env)
    delays = profile_delays(root, recipe)
    rng = random.Random(1000 + case.get("delay_seed", case["seed"]) + int(recipe["args"].get("latency_seed_offset", 0)))
    executor, history, requests, pending, planned = KeyExecutor(), [], [], None, -1
    horizon = round(duration * FPS)
    frame, lag_max, started = 0, 0.0, time.monotonic()
    pool = ThreadPoolExecutor(1) if mode == "realtime" else None
    status, error = "natural_end", None

    def deliver(row, answer_text, meta, apply_frame):
        nonlocal planned
        row.update(apply_frame=apply_frame, capture_to_apply_game_s=(apply_frame - row["capture_frame"]) / FPS,
                   call_wall_seconds=meta.get("wall_seconds"), output_tokens=meta.get("output_tokens"), answer=answer_text)
        try:
            answer = parse_answer(answer_text)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            row.update(status="invalid", error=str(exc)[:200])
            planned = -1  # declared rule: an unusable answer is discarded and a fresh screenshot is sent
            history.append(f"piece #{row['target']}: answer unusable ({str(exc)[:60]}) -> ignored")
            return
        row["status"] = executor.apply(answer, row["target"], apply_frame)
        if row["status"] == "applied":
            history.append(f"piece #{row['target']}: executed {answer['piece']} rot{answer['rot']} col{answer['col']}")
        else:
            history.append(f"piece #{row['target']}: answer arrived after it locked -> discarded")

    try:
        with (out / "steps.jsonl").open("w") as steps:
            while frame < horizon and not env.over:
                screen = render(env)
                executor.observe(screen)
                if pending is None and executor.piece_index != planned:
                    image = png(screen)
                    system, text = build_task(root, recipe, mode, history)
                    row = {"seq": len(requests), "capture_frame": frame, "target": executor.piece_index,
                           "image_sha256": hashlib.sha256(image).hexdigest(), "capture_wall_seconds": time.monotonic() - started}
                    planned = executor.piece_index
                    call_dir = out / "calls" / f"call-{row['seq']:05d}"
                    if provider == "rules":
                        answer_text, meta = client.act_on_truth(env)
                        call_dir.mkdir(parents=True); (call_dir / "result.json").write_text(json.dumps({"answer": answer_text, "meta": meta}))
                        future = None
                    elif mode == "simulation":
                        answer_text, meta = client.act(text, [image], call_dir)  # virtual clock waits for computation
                        future = None
                    else:
                        future = pool.submit(client.act, text, [image], call_dir)
                    if mode == "simulation":
                        sampled = rng.choice(delays)
                        row.update(sampled_delay_seconds=sampled, delivery_frame=frame + delay_frames(sampled, slowdown))
                        pending = (row, answer_text, meta, None)
                    else:
                        pending = (row, None, None, future)
                    requests.append(row)
                if pending is not None:
                    row, answer_text, meta, future = pending
                    if mode == "simulation" and frame >= row["delivery_frame"]:
                        deliver(row, answer_text, meta, frame); pending = None
                    elif mode == "realtime" and future.done():
                        answer_text, meta = future.result()
                        deliver(row, answer_text, meta, frame); pending = None
                action = executor.action(env.prev_action)
                env.step(action)
                steps.write(json.dumps({"frame": frame, "action": action, "lines": env.lines, "pieces": env.pieces}) + "\n")
                frame += 1
                if mode == "realtime":
                    target = started + frame * slowdown / FPS
                    now = time.monotonic()
                    if target > now:
                        time.sleep(target - now)
                    else:
                        lag_max = max(lag_max, now - target)
            if pending is not None and mode == "realtime":
                row, _, _, future = pending
                try:
                    answer_text, meta = future.result(timeout=300)
                    row.update(answer=answer_text, call_wall_seconds=meta.get("wall_seconds"), status="unapplied_after_horizon")
                except BaseException as exc:  # retained, not applied
                    row.update(status="unapplied_after_horizon", error=type(exc).__name__)
            elif pending is not None:
                pending[0].update(status="unapplied_after_horizon")
    except BaseException as exc:
        status, error = "interrupted", {"type": type(exc).__name__, "message": str(exc)[:500]}
        raise
    finally:
        if pool is not None:
            pool.shutdown(wait=True)
        with (out / "requests.jsonl").open("w") as log:
            for row in requests:
                log.write(json.dumps(row) + "\n")
        (out / "actions.json").write_text(json.dumps(executor.applied, indent=1))
        end = board_state(env)
        applied = [r for r in requests if r.get("status") == "applied"]
        ages = sorted(r["capture_to_apply_game_s"] for r in requests if "capture_to_apply_game_s" in r)
        summary = {"case": case, "mode": mode, "provider": provider, "slowdown": slowdown,
                   "frames": frame, "game_seconds": frame / FPS, "wall_seconds": time.monotonic() - started,
                   "start": start, "end": end, "lines": end["lines"] - start["lines"], "pieces": end["pieces"] - start["pieces"],
                   "new_holes": end["holes"] - start["holes"], "height_delta": end["height_sum"] - start["height_sum"],
                   "survived": not env.over, "calls": len(requests), "applied": len(applied),
                   "stale": sum(r.get("status") == "stale" for r in requests), "invalid": sum(r.get("status") == "invalid" for r in requests),
                   "capture_to_apply_game_s_median": statistics.median(ages) if ages else None,
                   "capture_to_apply_game_s_max": max(ages) if ages else None,
                   "max_frame_lag_seconds": lag_max if mode == "realtime" else None, "status": status, "error": error}
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def episodes_from(recipe: dict, args) -> list[dict]:
    if args.seed is not None:
        return [{"seed": args.seed, "level": args.level or 1, "prefix": args.prefix or 0}]
    return list(recipe["args"]["episodes"])


def run_recipe(root, recipe, out: Path, args, client_factory, mode: str, provider: str):
    duration = args.duration if args.duration is not None else recipe["args"]["duration"]
    slowdown = args.slowdown if args.slowdown is not None else float(recipe["args"].get("slowdown", 1))
    system, _ = build_task(root, recipe, mode)
    (out / "task-example.txt").write_text(build_task(root, recipe, mode)[1])
    client = client_factory(output=out / "transport-worker", system=system)
    summaries = []
    try:
        for i, case in enumerate(episodes_from(recipe, args)):
            name = f"episode-{i:02d}-s{case['seed']}-l{case['level']}-p{case.get('prefix', 0)}"
            try:
                summaries.append(run_episode(root, recipe, out / name, case, client, mode, provider, duration, slowdown))
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
                     "stale": sum(s["stale"] for s in summaries), "invalid": sum(s["invalid"] for s in summaries),
                     "capture_to_apply_game_s_median_of_medians": statistics.median(ages) if ages else None}
        (out / "summary.json").write_text(json.dumps({
            "mode": mode, "provider": provider, "clock": "virtual" if mode == "simulation" else "wall",
            "duration_game_seconds": duration, "slowdown": slowdown, "aggregate": aggregate, "episodes": summaries,
            "status": "interrupted" if any(s.get("status") == "interrupted" for s in summaries) else "completed",
            "limitation": ("Sampled measured delays; actor computation pauses the virtual clock." if mode == "simulation"
                           else "Actual response latency on a continuously advancing clock."),
        }, indent=2) + "\n")
    return summaries


def verify_replay(root, recipe, episode_dir: Path) -> dict:
    """Zero-model replay: rebuild the episode from its recorded answers and apply frames; check image hashes and outcome."""
    summary = json.loads((episode_dir / "summary.json").read_text())
    case = summary["case"]
    requests = [json.loads(line) for line in (episode_dir / "requests.jsonl").read_text().splitlines()]
    env = make_env(case["seed"], case["level"], case.get("prefix", 0))
    executor = KeyExecutor()
    by_capture = {r["capture_frame"]: r for r in requests}
    by_apply = {r["apply_frame"]: r for r in requests if "apply_frame" in r and r.get("status") in ("applied", "stale", "invalid")}
    checked = 0
    for frame in range(summary["frames"]):
        screen = render(env)
        executor.observe(screen)
        if frame in by_capture:
            digest = hashlib.sha256(png(screen)).hexdigest()
            if digest != by_capture[frame]["image_sha256"]:
                raise AssertionError(f"image mismatch at frame {frame}")
            checked += 1
        if frame in by_apply:
            row = by_apply[frame]
            if row["status"] != "invalid":
                status = executor.apply(parse_answer(row["answer"]), row["target"], frame)
                if status != row["status"]:
                    raise AssertionError(f"executor status mismatch at frame {frame}: {status} vs {row['status']}")
        env.step(executor.action(env.prev_action))
    end = board_state(env)
    if end != summary["end"] or (not env.over) != summary["survived"]:
        raise AssertionError("final board state does not match the recorded summary")
    return {"episode": episode_dir.name, "verified_frames": summary["frames"], "verified_requests": checked,
            "lines": summary["lines"], "survived": summary["survived"], "model_calls": 0}


def profile_inputs(root, recipe, episode_dir: Path, output: Path, client_factory, provider: str, max_calls: int) -> dict:
    """Strictly serial latency measurement: resend retained request inputs one at a time; no gameplay."""
    calls = sorted(p for p in (episode_dir / "calls").glob("call-*") if (p / "prompt.txt").exists() and (p / "image_0.png").exists())
    if not calls:
        raise ValueError("No retained request inputs (calls/*/prompt.txt + image_0.png) in " + str(episode_dir))
    system, _ = build_task(root, recipe, "realtime")
    client = client_factory(output=output.with_suffix("") / "transport", system=system)
    rows = []
    try:
        for call in calls[:max_calls]:
            text, image = (call / "prompt.txt").read_text(), (call / "image_0.png").read_bytes()
            started = time.monotonic()
            try:
                answer, meta = client.act(text, [image], output.with_suffix("") / "transport" / call.name)
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
               "definition": "wall seconds from sending the retained prompt+screenshot to receiving a complete, parseable answer"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, indent=1) + "\n")
    return {k: v for k, v in profile.items() if k != "rows"}
