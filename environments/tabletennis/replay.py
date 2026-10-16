"""Complete wall-time replay from independently recorded public camera images."""
import json
import math
from pathlib import Path
import subprocess

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont


def _wrap_pixels(text, font, width):
    lines = []
    for word in text.split():
        if lines and font.getlength(lines[-1] + " " + word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


def _execution_caption(state, frame, selection, leg, latest_id, finished):
    if finished:
        return "Match complete."
    if state.get("ball") == "your serve":
        return "Executing: synchronized RULE service."
    if selection is None or leg[0] != state["point"]:
        return "Intent accepted; awaiting next stroke."
    current_leg = (state["point"], state.get("ball"), round(frame-state["t_since_played"]*100))
    origin = selection["intent_id"]
    if current_leg != leg:
        choice = selection["policy"] if selection["selected"] else "RULE geometry fallback"
        return f'Last return: {choice} / reply #{origin}.'
    caption = (f'Executing: {selection["policy"]} / reply #{origin}.' if selection["selected"]
               else f'RULE geometry fallback; requested {selection["policy"]}.')
    if origin != latest_id:
        caption += f" Reply #{latest_id} awaits next flight."
    return caption


def export_replay(output):
    output = Path(output)
    if (output / "presentation.jsonl").exists():
        return export_physical_replay(output)
    summary = json.loads((output / "summary.json").read_text())
    captures = [json.loads(line) for line in (output / "captures.jsonl").read_text().splitlines()]
    ticks = [json.loads(line) for line in (output / "physics.jsonl").read_text().splitlines()]
    ticks.sort(key=lambda row: row["wall_mono"])
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    intentions = [event for event in events if event["event"] == "intent_accepted"]
    started = summary["started_mono"]
    duration = max(summary["ended_mono"], captures[-1]["available_mono"]) - started
    fps, tail = 20, .5
    video = output / "wallclock.mp4"
    process = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "960x432", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(video)], stdin=subprocess.PIPE)
    camera_i = tick_i = intent_i = 0
    policy, executed_policy, score = "reference", "reference", {"you": 0, "opponent": 0}
    native_frame = 0
    font = ImageFont.load_default(size=16)
    try:
        for index in range(math.ceil((duration + tail) * fps)):
            wall = index / fps
            now = started + wall
            while camera_i + 1 < len(captures) and captures[camera_i + 1]["available_mono"] <= now:
                camera_i += 1
            while tick_i < len(ticks) and ticks[tick_i]["wall_mono"] <= now:
                event = ticks[tick_i]
                if event["event"] == "tick":
                    native_frame = event["frame"]
                if event["event"] == "native_event" and event["native_event"]["kind"] == "point":
                    values = event["native_event"]["score"]
                    score = {"you": values[0], "opponent": values[1]}
                if event["event"] == "planned_action":
                    feedback = event["feedback"]
                    if not any(key in feedback for key in ("discarded", "rejected", "kept")):
                        selected = event["request"]["selection"]
                        executed_policy = selected["policy"] if selected and selected["selected"] else "reference"
                tick_i += 1
            while intent_i < len(intentions) and intentions[intent_i]["wall_mono"] <= now:
                policy = intentions[intent_i]["intent"]["policy"]
                intent_i += 1
            capture = captures[camera_i]
            image = Image.new("RGB", (960, 432), "#101720")
            with Image.open(output / "images" / Path(capture["image"]).name) as sheet:
                image.paste(sheet.crop((1440, 0, 1920, 360)).convert("RGB"), (0, 56))
                image.paste(sheet.crop((1440, 360, 1920, 720)).convert("RGB"), (480, 56))
            draw = ImageDraw.Draw(image)
            draw.text((12, 5), f'WALL {min(wall, duration):.2f}s   GAME {native_frame / 100:.2f}s   '
                      f'SCORE {score["you"]}:{score["opponent"]}', fill="white", font=font)
            draw.text((12, 29), f'GPT {policy}   STROKE {executed_policy}   CAMERA k={capture["frame"]}   '
                      f'{"FINAL" if wall >= duration else "LIVE 1x target / no catch-up"}',
                      fill="#b2d8ef", font=font)
            process.stdin.write(image.tobytes())
    finally:
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Wall-clock replay encoding failed")
    result = {"video": str(video), "timeline": "complete actual wall time, uncut",
              "live_wall_seconds": duration, "final_hold_seconds": tail, "fps": fps,
              "frames": math.ceil((duration + tail) * fps), "capture_count": len(captures),
              "game_seconds": summary["game_seconds"],
              "score": [summary["points_for"], summary["points_against"]]}
    (output / "replay.json").write_text(json.dumps(result, indent=2))
    return result


def export_physical_replay(output):
    """Render every physical pose offline; no hidden state reaches the live actor."""
    import numpy as np
    from .native import ROOT, load_plugin
    sport = load_plugin(ROOT / "sports/tabletennis/plugin.py")
    # Reuse the environment's exact visual model and public camera poses.
    import sys
    renderer = sport.worker_init.__func__.__globals__["MatchView"]()
    renderer.r.close()
    renderer.m.vis.global_.offwidth = 960
    renderer.m.vis.global_.offheight = 720
    renderer.r = renderer.mj.Renderer(renderer.m, height=720, width=960)
    reference = sport.players()["reference"]
    Cam = sys.modules[reference.__module__].Cam
    cameras = [Cam(cam) for cam in renderer.Match.CAM_INFO]
    summary = json.loads((output / "summary.json").read_text())
    poses = [json.loads(line) for line in (output / "presentation.jsonl").read_text().splitlines()]
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    intentions = [ev for ev in events if ev["event"] == "intent_accepted"]
    physical_events = [json.loads(line) for line in (output / "physics.jsonl").read_text().splitlines()]
    applications = [ev for ev in physical_events if ev["event"] == "planned_action"
                    and not any(k in ev["feedback"] for k in ("discarded", "rejected", "kept"))]
    started, ended = summary["started_mono"], summary["ended_mono"]
    duration = ended - started
    fps, tail = 50, 1
    video = output / "wallclock.mp4"
    process = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(video)], stdin=subprocess.PIPE)
    title = ImageFont.truetype("DejaVuSans.ttf", 40)
    font = ImageFont.truetype("DejaVuSans.ttf", 30)
    small = ImageFont.truetype("DejaVuSans.ttf", 24)
    history_font = ImageFont.truetype("DejaVuSans.ttf", 22)
    footer = ImageFont.truetype("DejaVuSans.ttf", 18)
    pose_i = intent_i = application_i = 0
    accepted_intent = applied_intent = None
    applied_leg = None
    policy, previous_point, reset_at = "reference", 1, -100
    display_log = (output / "display_timeline.jsonl").open("w")
    try:
        for index in range(math.ceil((duration + tail) * fps)):
            wall = index / fps
            now = started + wall
            while pose_i + 1 < len(poses) and poses[pose_i + 1]["wall_mono"] <= now:
                pose_i += 1
            while intent_i < len(intentions) and intentions[intent_i]["wall_mono"] <= now:
                policy = intentions[intent_i]["intent"]["policy"]
                accepted_intent = intentions[intent_i]
                intent_i += 1
            while application_i<len(applications) and applications[application_i]["wall_mono"]<=now:
                selected = applications[application_i]["request"]["selection"]
                if selected is not None:
                    applied_intent = selected
                    applied_leg = tuple(applications[application_i]["request"]["leg_key"])
                application_i += 1
            pose = poses[pose_i]
            state, ball = pose["state"], np.array(pose["qpos"][:3])
            if state["point"] != previous_point:
                previous_point, reset_at = state["point"], wall
            image = Image.new("RGB", (1920, 1080), "#0c1420")
            for ci, camera in enumerate(cameras):
                tile = Image.fromarray(renderer.tile(ci, pose["qpos"], "",
                    lambda scene: renderer.Match._extra_geoms(None, scene, pose["opp_x"]), pose["opp_x"]))
                overlay = ImageDraw.Draw(tile)
                # Highlight the recorded ball, including brief occlusion. Never
                # invent an interpolated flight across a reset/toss placement.
                if ball[2] >= -.03:
                    trail = [p for p in poses[max(0, pose_i-12):pose_i+1]
                             if p["state"]["point"] == state["point"] and p["qpos"][2] >= -.03]
                    xy = [(2*camera.project(p["qpos"][:3])[0], 2*camera.project(p["qpos"][:3])[1]) for p in trail]
                    if len(xy) > 1:
                        overlay.line(xy, fill="#f9bd61", width=3)
                    x, y = camera.project(ball)
                    x, y = 2*x, 2*y
                    overlay.ellipse((x-11, y-11, x+11, y+11), outline="#ff713d", width=3)
                if ci == 0:
                    image.paste(tile.resize((1280, 960), Image.Resampling.LANCZOS), (24, 84))
                else:
                    image.paste(tile.resize((426, 320), Image.Resampling.LANCZOS), (44, 704))
            draw = ImageDraw.Draw(image)
            draw.rectangle((23, 83, 1304, 1044), outline="#40536c", width=1)
            draw.rectangle((43, 703, 470, 1024), outline="#718093", width=1)
            score = state["score"]
            display_point = min(state["point"], len(summary["points"]))
            sv = state.get("serve") or {}
            phase = "BALL IN TOSS DEVICE" if ball[2] < -.03 and state.get("ball_state") == "your serve" else state["ball_state"].upper()
            if sv.get("phase") in ("waiting", "open", "tossed"):
                phase = f'{sv.get("server", "").upper()} SERVE: {sv["phase"].upper()} / {phase}'
            label = "FINAL" if wall >= duration else "POINT RESET / NEW SERVICE" if wall-reset_at < .65 else phase
            source_label = "REAL API / 1x" if accepted_intent else "PURE RULE BASELINE"
            draw.text((24, 18), "SOOOOL | TABLE TENNIS | " + source_label, fill="#8bd2ff", font=title)
            draw.text((42, 100), f'k={pose["frame"]}  t={pose["frame"]/100:.2f}s',
                      fill="white", font=small, stroke_width=1, stroke_fill="#40536c")
            x = 1344
            draw.text((x, 30), "LIVE DECISION SUMMARY", fill="#8bd2ff", font=font)
            draw.text((x, 102), f'Robot {score["you"]} : {score["opponent"]} Opponent', fill="white", font=font)
            draw.text((x, 150), f'Game {pose["frame"]/100:.2f}s | Wall {min(wall,duration):.2f}s',
                      fill="#a8b6c8", font=small)
            for i, line in enumerate(_wrap_pixels(f'Point {display_point} | {label.replace("_", " ")}', footer, 544)):
                draw.text((x, 192 + i * 23), line, fill="#a8b6c8", font=footer)
            if accepted_intent is None:
                brief = "Pure rule baseline. No model decisions."
                execution = "Rule service and return control."
            else:
                ident = accepted_intent["request_id"]
                source = accepted_intent["source_frame"]
                age = max(0, (pose["frame"]-source)/100)
                brief = accepted_intent["intent"].get("decision_summary", "")
                draw.text((x, 492), "NEXT: " + policy.replace("_", " / ").upper(), fill="#f1ce79", font=font)
                timing = "pre-clock initialization" if accepted_intent.get("bootstrap") else f'obs to accept {accepted_intent["latency_wall_seconds"]:.2f}s'
                draw.text((x, 540), f'Reply #{ident} | {timing}', fill="#a8b6c8", font=history_font)
                draw.text((x, 576), f'Observed game {source/100:.2f}s | age {age:.2f}s', fill="#a8b6c8", font=history_font)
                execution = _execution_caption(state, pose["frame"], applied_intent, applied_leg, ident, wall >= duration)
                inflight = sum(e["event"]=="request_issued" and not e.get("bootstrap") for e in events if e["wall_mono"]<=now)
                inflight -= sum(e["event"]=="reply_received" and not e.get("bootstrap") for e in events if e["wall_mono"]<=now)
                worker_text = (f'{summary.get("model_workers",1)} model workers | gameplay stopped' if wall >= duration else
                               f'{summary.get("model_workers",1)} model workers | {inflight} requests in flight')
                draw.text((x, 718), worker_text,
                          fill="#a8b6c8", font=history_font)
            draw.text((x, 232), "LATEST ACCEPTED MODEL SUMMARY", fill="#a8b6c8", font=footer)
            for size in range(40, 9, -2):
                brief_font = ImageFont.truetype("DejaVuSans.ttf", size)
                brief_lines = _wrap_pixels(brief, brief_font, 544)
                if len(brief_lines) * (size + 6) <= 224:
                    break
            for i, line in enumerate(brief_lines):
                draw.text((x, 260 + i * (size + 6)), line, fill="white", font=brief_font)
            for i, line in enumerate(_wrap_pixels(execution, history_font, 544)):
                draw.text((x, 630 + i * 29), line, fill="#a8b6c8", font=history_font)
            draw.text((x, 778), "RECENT MODEL SUMMARIES", fill="#8bd2ff", font=small)
            y = 824
            for previous in intentions[max(0, intent_i-4):max(0, intent_i-1)][::-1]:
                lines = _wrap_pixels(previous["intent"].get("decision_summary", ""), history_font, 544)
                if y + len(lines) * 29 > 1044:
                    break
                for line in lines:
                    draw.text((x, y), line, fill="#a8b6c8", font=history_font)
                    y += 29
                y += 15
            draw.text((24, 1053), "Recorded native poses | 1x actual wall time | 50 FPS | Same-response model summaries | Orange ring / trail: offline ball highlight (includes occlusion)",
                      fill="#a8b6c8", font=footer)
            display_log.write(json.dumps({"video_frame": index, "video_seconds": wall,
                "native_frame": pose["frame"], "pose_wall_mono": pose["wall_mono"],
                "reply_id": accepted_intent["request_id"] if accepted_intent else None,
                "summary": brief, "execution_caption": execution,
                "applied_intent_id": applied_intent["intent_id"] if applied_intent else None,
                "applied_policy": applied_intent["policy"] if applied_intent else None,
                "applied_leg": applied_leg}) + "\n")
            process.stdin.write(image.tobytes())
    finally:
        display_log.close()
        renderer.r.close()
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Physical replay encoding failed")
    result = {"video": str(video), "timeline": "complete actual wall time, uncut; every native pose recorded",
              "live_wall_seconds": duration, "final_hold_seconds": tail, "fps": fps,
              "frames": math.ceil((duration+tail)*fps), "physical_pose_count": len(poses),
              "presentation": "badminton-style navy frame, main camera with inset, live decision summary and recent model summaries; offline ball highlight",
              "video_dimensions": [1920,1080],
              "display_timeline": "display_timeline.jsonl",
              "game_seconds": summary["game_seconds"], "score": [summary["points_for"], summary["points_against"]]}
    (output / "replay.json").write_text(json.dumps(result, indent=2))
    (output / "decision_timeline.json").write_text(json.dumps({
        "summary_type": "verbatim model public decision_summary, not private chain of thought",
        "accepted": intentions,
        "installed_returns": [{"frame": e["frame"], "wall_mono":e["wall_mono"],
                               "selection":e["request"]["selection"]} for e in applications
                              if e["request"]["selection"] is not None]}, indent=2))
    return result
