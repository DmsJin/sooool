"""Render retained public camera frames and summarize independently audited episodes."""
import html
import json
import os
from pathlib import Path
import subprocess
import tempfile

import imageio_ffmpeg
from PIL import Image, ImageDraw


def video_episode(path, observations, frames):
    """Hold public observations at 10 FPS and display both newest camera tiles."""
    with tempfile.TemporaryDirectory(prefix="badminton-video-") as temp:
        index = 0
        for number, frame in enumerate(range(0, frames, 10)):
            while index + 1 < len(observations) and observations[index + 1]["frame"] <= frame:
                index += 1
            observation = observations[index]
            image_path = path / "images" / Path(observation["images"][-1]["path"]).name
            with Image.open(image_path) as sheet:
                image = Image.new("RGB", (960, 392), "#161d28")
                image.paste(sheet.crop((1440, 0, 1920, 360)).convert("RGB"), (0, 32))
                image.paste(sheet.crop((1440, 360, 1920, 720)).convert("RGB"), (480, 32))
            score = observation["state"]["score"]
            ImageDraw.Draw(image).text((12, 10),
                f'{path.name}  game {frame / 100:.1f}s  score {score["you"]}:{score["opponent"]}  '
                f'observation {observation["frame"] / 100:.1f}s', fill="white")
            image.save(Path(temp) / f"frame-{number:06d}.png")
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y", "-framerate", "10",
                        "-i", str(Path(temp) / "frame-%06d.png"), "-c:v", "libx264", "-crf", "20",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path / "1x.mp4")], check=True)


def report_round(directory, episodes):
    """Keep development scores, model authority and replay integrity separate."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    sections = []
    for episode in episodes:
        path = Path(episode).resolve()
        summary = json.loads((path / "summary.json").read_text())
        audit = json.loads((path / "audit.json").read_text())
        if not audit["matched"]:
            raise ValueError(f"Replay mismatch: {path.name}")
        events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
        selections = [e["selection"] for e in events if e["event"] == "executed"
                      and not e["invalid_action"] and e["selection"] is not None]
        row = {"episode": path.name, "summary": summary,
               "actual_model_generation_calls": len(list((path / "requests").glob("request-*/events.jsonl"))),
               "audit": {k: v for k, v in audit.items() if k != "trajectory"},
               "changed_rally_choices": sum(s["kind"] == "rally" and s["changed_from_rule"] for s in selections),
               "changed_recoveries": sum(s["kind"] == "recovery" and s["changed_from_rule"] for s in selections)}
        rows.append(row)
        observations = [e for e in events if e["event"] == "observation"]
        video_episode(path, observations, summary["frames"])
        relative = html.escape(os.path.relpath(path / "1x.mp4", directory), quote=True)
        sections.append(f'<h2>{html.escape(path.name)}</h2>'
                        f'<p>Score {summary["points_for"]}:{summary["points_against"]}; '
                        f'legal returns {audit["legal_returns"]}/{audit["incoming"]}; '
                        f'logical requests {summary["calls"]}; actual generations {row["actual_model_generation_calls"]}; '
                        f'accepted intentions {summary["accepted"]}.</p>'
                        f'<video controls preload="metadata" src="{relative}"></video>')
    result = {"evidence_class": "fresh_subscription_simulation", "episodes": rows,
              "protocol": "L1/S2; 100 Hz physics; up to 10 Hz public observations; serial default-tier SOL; historical API delay injection",
              "video_protocol": "10 FPS held public observations; two newest camera tiles; 1x game speed",
              "real_time_api_acceptance": False}
    (directory / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    (directory / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Badminton tactical control</title>'
        '<style>body{max-width:1100px;margin:30px auto;background:#101620;color:#eee;font:16px sans-serif}'
        'video{width:100%}a{color:#8cd}</style><h1>Badminton tactical control</h1>'
        '<p>L1/S2, EGL GPU rendering, native 100 Hz physics. Fresh subscription simulations with Fast disabled. '
        'Historical API delays schedule decisions. Each video shows game time at 1x.</p>'
        '<p><a href="comparison.json">Scores, accepted intentions and replay audits</a></p>' + ''.join(sections))
    return result
