"""Audit recorded native controls, then render paced replays with public summaries."""
import html
import json
from pathlib import Path
import subprocess
import sys
import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .runner import _write
from .tactics import _flights, _placement


def _replay(directory):
    # Native/GPU dependencies remain optional for model-boundary tests.
    from .native import Action, BadmintonEnvironment
    run = json.loads((directory / "run.json").read_text())
    summary = json.loads((directory / "summary.json").read_text())
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    observations = {e["frame"]: e for e in events if e["event"] == "observation"}
    executions = {e["frame"]: e for e in events if e["event"] == "executed"}
    resets = {e["frame"] for e in events if e["event"] == "soft_reset"}
    by_frame = {}
    for event in events:
        by_frame.setdefault(event["frame"], []).append(event)
    env = BadmintonEnvironment(level=run["config"]["level"], seed=run["seed"],
                              max_env_steps=run["window_steps"] + 1, slowdown=run["config"]["slowdown"])
    strokes, current_stroke = {}, None
    try:
        env.reset(render=False)
        for frame in range(summary["frames"]):
            # The live loop installs ready controls before capturing this step's public state.
            if frame in executions:
                execution = executions[frame]
                applied = env.match.apply("A", execution["action"])
                for key, value in applied.items():
                    if execution["action_result"][key] != value:
                        raise ValueError(f"Native execution feedback differs at frame {frame}")
                selection = execution["selection"]
                if selection is not None and selection["kind"] == "rally" and "rejected" not in applied:
                    current_stroke = tuple(selection["stroke_id"])
                    if current_stroke not in strokes:
                        strokes[current_stroke] = {"first_frame": frame, "initial": selection,
                                                   "result_index": len(env.match.g.results)}
                    strokes[current_stroke]["final"] = selection
            if frame in observations:
                expected = {k: v for k, v in observations[frame]["state"].items() if k != "pending_commands"}
                if env.public_state() != expected:
                    raise ValueError(f"Native public state differs at frame {frame}")
            yield env, frame, by_frame.get(frame, []), strokes
            hit_before = env.match.g.leg.get("hit")
            result = env.step(Action(None, "noop", True))
            if current_stroke is not None and hit_before is None and env.match.g.leg.get("hit") is not None:
                # Offline diagnostic truth stays outside policy observations and API prompts.
                bp = sys.modules[env.sport.players()["reference"].__module__]
                position, velocity = np.asarray(env.match.g.s.sh_p), np.asarray(env.match.g.s.sh_v)
                speed = float(np.linalg.norm(velocity))
                normal = velocity / speed
                landing, clearance = _flights(bp, position[None], np.zeros((1, 3)), normal[None],
                                              np.array([speed / bp.GAIN]), bp.DT)
                selection = strokes[current_stroke]["final"]
                placement = _placement(bp, selection["requested_choice"], selection["requested_target"], landing[0], normal)
                strokes[current_stroke]["realized_launch"] = {
                    "frame": frame + 1, "landing_without_opponent_interception": placement["predicted_landing"],
                    "target_error_m": placement["target_error_m"], "goal_status": placement["goal_status"],
                    "net_clearance_m": None if np.isnan(clearance[0]) else float(clearance[0]),
                    "legal_flight": bool(clearance[0] > 0 and abs(landing[0, 0]) <= bp.COURT_X
                                         and 0 < landing[0, 1] <= bp.COURT_Y)}
            if bool(result.info.get("soft_reset")) != (frame + 1 in resets):
                raise ValueError(f"Native point boundary differs at frame {frame}")
            if result.info.get("soft_reset") or (current_stroke is not None
                    and len(env.match.g.results) > strokes[current_stroke]["result_index"]):
                current_stroke = None
        metrics = result.info["task_metrics"]
        if (any(metrics[k] != summary[k] for k in ("points_for", "points_against"))
                or result.done != summary["native_match_completed"]):
            raise ValueError("Native final score or termination differs")
        for stroke in strokes.values():
            index = stroke["result_index"]
            stroke["outcome"] = env.match.g.results[index] if index < len(env.match.g.results) else None
    finally:
        env.close()


def audit_realtime(directory):
    """Verify the saved action sequence without new model generation."""
    directory = Path(directory)
    report = {"matched": False, "model_calls": 0}
    try:
        for env, frame, _, strokes in _replay(directory):
            match = env.match
        results = match.g.results
        incoming = [r for r in results if r["kind"] != "our_serve" and not (r["returned"] and not r["hit"])]
        serves = [r for r in results if r["kind"] == "our_serve"]
        report.update(matched=True, verified_frames=frame + 1, incoming=len(incoming),
                      legal_returns=sum(r["returned"] for r in incoming), serves=len(serves),
                      legal_serves=sum(r["returned"] for r in serves))
        sol = [s for s in strokes.values() if s["initial"]["goal_origin"] == "sol"]
        settled = [s for s in sol if s["outcome"] is not None]
        realized = [s for s in settled if "realized_launch" in s]
        report["goal_strokes"] = list(strokes.values())
        report["goal_execution"] = {
            "controlled_strokes": len(strokes), "sol_strokes": len(sol), "settled_sol_strokes": len(settled),
            "planned_exact": sum(s["final"]["goal_status"] == "exact" for s in sol),
            "planned_projected": sum(s["final"]["goal_status"] == "projected" for s in sol),
            "rule_fallback": sum(s["final"]["goal_status"] == "rule_fallback" for s in sol),
            "changed_from_rule": sum(s["initial"]["changed_from_rule"] for s in sol),
            "realized_hits": len(realized),
            "realized_legal": sum(s["outcome"]["returned"] and s["outcome"]["hit"] for s in settled),
            **{f"realized_{kind}": sum(s["realized_launch"]["goal_status"] == kind
                    and s["realized_launch"]["legal_flight"] and s["outcome"]["returned"] for s in realized)
               for kind in ("exact", "projected")}}
    except ValueError as exc:
        report["error"] = str(exc)
    _write(directory / "audit.json", report)
    return report


def decision_panel(events, current, history):
    """Update display state only at recorded acceptance, execution and point events."""
    current = dict(current)
    for event in events:
        if event["event"] == "intent_accepted":
            current.update(brief=event["brief"], intent=event["intent"], id=event["id"],
                           latency=event["capture_to_accept_seconds"], status="Intent accepted; awaiting next stroke")
            history.append(event["brief"])
        elif event["event"] == "executed":
            selection = event["selection"]
            if selection is None:
                current["status"] = "Reference serving / racket execution"
            elif selection["kind"] == "rally":
                choice = selection["requested_choice"]
                current["status"] = (f'{selection["goal_origin"].upper()} {selection["branch"]}: '
                                     f'{choice["side"]} / {choice["shot"]}; {selection["goal_status"]} plan')
            else:
                current["status"] = "Recovery command applied"
        elif event["event"] == "soft_reset":
            current = {"brief": "New point; waiting for a model decision.", "intent": None,
                       "status": "Reference serving / tracking"}
    return current


def report_realtime(directory):
    """Encode one frame per native control step at the recorded slowdown."""
    # Encoding dependencies are optional for the pure panel and transport contracts.
    import imageio_ffmpeg
    directory = Path(directory).resolve()
    audit = json.loads((directory / "audit.json").read_text())
    if not audit["matched"]:
        raise ValueError("Video requires a matched native replay")
    summary = json.loads((directory / "summary.json").read_text())
    slowdown = json.loads((directory / "run.json").read_text())["config"]["slowdown"]
    fps = 100 / slowdown
    period = slowdown / 100
    video_name = f"realtime-s{slowdown}.mp4"
    source_label = f"REAL API / S{slowdown}" if summary["mode"] == "realtime_api" else "PREFLIGHT / ZERO API CALLS"
    font = ImageFont.truetype("DejaVuSans.ttf", 23)
    small = ImageFont.truetype("DejaVuSans.ttf", 17)
    title = ImageFont.truetype("DejaVuSans.ttf", 30)
    encoder = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo",
        "-pix_fmt", "rgb24", "-s", "1440x800", "-r", f"100/{slowdown}", "-i", "-", "-an", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(directory / video_name)], stdin=subprocess.PIPE)
    current = {"brief": "Waiting for the first model response.", "intent": None,
               "status": "Reference serving / tracking"}
    history = []
    renderer = None
    try:
        for env, frame, events, _ in _replay(directory):
            if renderer is None:
                renderer = env.sport.worker_init("render", "A", env._cfg)
            current = decision_panel(events, current, history)
            g = env.match.g
            snap = {"qpos": g.s.d.qpos.copy(), "sh": tuple(g.s.sh_p), "shv": tuple(g.s.sh_v),
                    "opp": g.opp_xy().copy(), "k": frame, "t": frame / 100}
            main = Image.fromarray(renderer.tile(0, snap)).resize((960, 720), Image.Resampling.LANCZOS)
            second = Image.fromarray(renderer.tile(1, snap)).resize((320, 240), Image.Resampling.LANCZOS)
            image = Image.new("RGB", (1440, 800), "#0c1420")
            image.paste(main, (16, 64))
            image.paste(second, (32, 528))
            draw = ImageDraw.Draw(image)
            draw.text((20, 15), "SOOOOL | BADMINTON | " + source_label, font=title, fill="#8bd2ff")
            draw.text((1008, 26), "LIVE DECISION SUMMARY", font=font, fill="#8bd2ff")
            score = env.public_state()["score"]
            draw.text((1008, 76), f'Robot {score["you"]} : {score["opponent"]} Opponent', font=font, fill="white")
            draw.text((1008, 115), f'Game {frame / 100:.2f}s | Wall {frame * period:.2f}s', font=small, fill="#a8b6c8")
            brief_lines = []
            for word in current["brief"].split():
                if brief_lines and title.getlength(brief_lines[-1] + " " + word) <= 400:
                    brief_lines[-1] += " " + word
                else:
                    brief_lines.append(word)
            for i, line in enumerate(brief_lines):
                draw.text((1008, 180 + i * 36), line, font=title, fill="white")
            intent = current["intent"]
            if intent is not None:
                normal = intent["normal"]
                draw.text((1008, 315), f'Normal: {normal["side"]} / {normal["shot"]}', font=font, fill="#f1ce79")
                draw.text((1008, 356), f'Recovery: {intent["recovery"]}', font=small, fill="#a8b6c8")
                draw.text((1008, 389), f'Reply #{current["id"]} | obs to accept {current["latency"]:.2f}s',
                          font=small, fill="#a8b6c8")
            for i, line in enumerate(textwrap.wrap(current["status"], width=34)):
                draw.text((1008, 440 + i * 27), line, font=small, fill="#a8b6c8")
            draw.text((1008, 530), "RECENT MODEL SUMMARIES", font=small, fill="#8bd2ff")
            y = 568
            for brief in history[-4:-1][::-1]:
                for line in textwrap.wrap(brief, width=34):
                    draw.text((1008, y), line, font=small, fill="#a8b6c8")
                    y += 24
                y += 12
            draw.text((20, 780), f"Verified replay of actual API controls | S{slowdown} playback | {fps:g} FPS | Same-response English summaries",
                      font=small, fill="#a8b6c8")
            encoder.stdin.write(image.tobytes())
    finally:
        if renderer is not None:
            renderer.r.close()
        encoder.stdin.close()
        code = encoder.wait()
    if code:
        raise RuntimeError("Video encoding failed")
    renderer_source = directory / "video_source" / "realtime_report.py"
    renderer_source.parent.mkdir(exist_ok=True)
    renderer_source.write_text(Path(__file__).read_text())
    metadata = {"source_mode": summary["mode"], "render_mode": "verified_native_action_replay",
                "renderer_source": "video_source/realtime_report.py",
                "fps": fps, "slowdown": slowdown, "video_seconds": summary["frames"] * period,
                "verified_frames": summary["frames"], "new_model_calls": 0, "summary_source": "same API response as intent"}
    _write(directory / "video.json", metadata)
    (directory / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Badminton realtime API</title>'
        '<style>body{background:#0c1420;color:#eee;max-width:1440px;margin:30px auto;font:18px sans-serif}video{width:100%}a{color:#8bd2ff}</style>'
        f'<h1>Badminton — {source_label}</h1><p>Verified native replay with recorded decision summaries.</p>'
        f'<p>Score {summary["points_for"]}:{summary["points_against"]}; API calls {summary["calls"]}; '
        f'cost ${html.escape(summary["cost_usd"])}; complete {summary["complete"]}.</p>'
        f'<video controls preload="metadata" src="{video_name}"></video>'
        '<p><a href="summary.json">Run summary</a> · <a href="audit.json">Replay audit</a></p>')
    return metadata
