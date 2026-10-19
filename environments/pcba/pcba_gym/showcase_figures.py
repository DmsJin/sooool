"""README explainer figures from a retained run: step close-ups, model-input GIF, pipeline timeline.

Offline only, zero model calls. Close-ups use the render-only showcase skin; the
model-input GIF uses the exact PNGs sent with each executed reply.
"""
import argparse
import json
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .showcase import Run, export_clip, wrap, BG, FG, DIM, ACC, OUT
from .scene import font

# Selected run (pcba-sim-belt2-timed-v2-s0-ls0): first board PCBA-005.
CLIPS = [('1-intercept', 6, 8, {'lookat': [-0.38, -0.02, 0.82], 'distance': 0.95, 'azimuth': 145, 'elevation': -38},
          '1 · Predict and intercept the moving board'),
         ('2-seat', 15, 9, {'lookat': [0.0, -0.08, 0.82], 'distance': 0.62, 'azimuth': 120, 'elevation': -30},
          '2 · Align on the pins and seat'),
         ('3-test-sort', 25.5, 11.5, {'lookat': [0.36, 0.06, 0.86], 'distance': 1.1, 'azimuth': 105, 'elevation': -30},
          '3 · Test, read FAIL, sort to the red magazine')]


def model_view_gif(run, out, until=38., width=720):
    W, IH = 960, 360; frames = []
    for ch in run.chunks:
        if ch['started_s'] > until: break
        seq = ch['sequence']; c = run.calls[seq]; d0 = run.source / f'call-{seq:03d}' / 'model'
        img = Image.new('RGB', (W, IH + 150), BG)
        img.paste(Image.open(d0 / 'image_0.png').convert('RGB').resize((480, 360), Image.LANCZOS), (0, 0))
        wrist = d0 / 'image_1.png'
        if wrist.exists():
            img.paste(Image.open(wrist).convert('RGB').resize((480, 360), Image.LANCZOS), (480, 0))
        d = ImageDraw.Draw(img)
        if not wrist.exists():
            d.text((720, 180), 'wrist image not sent\n(added only near the fixture\nor low over the pick lane)',
                   font=font(20), fill=DIM, anchor='mm', align='center')
        for x, lab in ((8, 'TOP CAMERA'), (488, 'WRIST CAMERA')):
            d.rounded_rectangle((x, 8, x + 150, 34), radius=6, fill=BG); d.text((x + 10, 12), lab, font=font(16, True), fill=ACC)
        y = IH + 12
        d.text((16, y), f"Input of reply #{seq:02d} · captured {c['capture_s']:.1f} s · executed from {ch['started_s']:.1f} s "
                        f"({ch['source_age_at_start_s']:.1f} s old)", font=font(19, True), fill=FG); y += 32
        for ln in wrap(d, run.answers.get(seq, {}).get('summary', ''), font(24, True), W - 32)[:2]:
            d.text((16, y), ln, font=font(24, True), fill=OUT); y += 32
        for ln in wrap(d, 'memory: ' + run.answers.get(seq, {}).get('memory', ''), font(17), W - 32)[:2]:
            d.text((16, y), ln, font=font(17), fill=DIM); y += 22
        frames.append(img.resize((width, int((IH + 150) * width / W)), Image.LANCZOS))
    pal = [f.convert('P', palette=Image.ADAPTIVE, colors=128) for f in frames]
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=1800, loop=0, optimize=True)


def timeline_png(run, out, t0=0, t1=42, board='PCBA-005'):
    r = run.report; S = 2; W, H = 1600 * S, 600 * S
    SURF, INK, INK2, GRID = '#1a1a19', '#f0efec', '#c3c2b7', '#3a3a37'
    EXEC, DROP = '#3987e5', '#d95926'   # dark categorical slots 1-2, validated against SURF
    F = lambda size, bold=False: ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans' + ('-Bold' if bold else '') + '.ttf', size * S)
    img = Image.new('RGB', (W, H), SURF); d = ImageDraw.Draw(img)
    X0, X1 = 190 * S, 1560 * S
    x = lambda t: X0 + (X1 - X0) * (t - t0) / (t1 - t0)
    d.text((40 * S, 26 * S), f'How replies reach the robot: first board of the selected run ({t0}–{t1} s)', font=F(26, True), fill=INK)
    d.text((40 * S, 64 * S), 'Each bar runs from image capture to the moment the reply may act (modeled delay). Only a reply whose parent chunk finished and whose guards match is executed.',
           font=F(15), fill=INK2)
    lx, ly = 40 * S, 98 * S
    for col, lab in ((EXEC, 'reply executed'), (DROP, 'reply dropped (superseded / rejected)')):
        d.rounded_rectangle((lx, ly + 3 * S, lx + 26 * S, ly + 17 * S), radius=4 * S, fill=col)
        d.text((lx + 34 * S, ly), lab, font=F(15), fill=INK); lx += (60 + len(lab) * 9) * S
    lanes = {0: ('Worker A', 175), 1: ('Worker B', 245), 'robot': ('Robot', 335), 'events': ('Board', 425)}
    for lab, yy in lanes.values():
        d.text((40 * S, (yy - 10) * S), lab, font=F(17, True), fill=INK)
    for t in range(t0, t1 + 1, 5):
        d.line((x(t), 150 * S, x(t), 470 * S), fill=GRID, width=S)
        d.text((x(t), 478 * S), f'{t} s', font=F(14), fill=INK2, anchor='mt')

    def bar(a_s, b_s, yy, col, h=26):
        a, b = x(max(a_s, t0)), x(min(b_s, t1))
        if b > a: d.rounded_rectangle((a, (yy - h / 2) * S, max(a + 4 * S, b - 2 * S), (yy + h / 2) * S), radius=4 * S, fill=col)

    def label(text, a_s, b_s, yy):
        if d.textlength(text, font=F(13, True)) + 12 * S < x(min(b_s, t1)) - x(a_s):
            d.text((x(a_s) + 6 * S, (yy - 8) * S), text, font=F(13, True), fill=SURF); return True
        return False

    for c in r['calls']:
        if c['capture_s'] > t1: continue
        yy = lanes[c['worker']][1]
        bar(c['capture_s'], c['ready_s'], yy, EXEC if c.get('selected_s') is not None else DROP)
        label(f"#{c['sequence']}", c['capture_s'], c['ready_s'], yy)
    for ch in r['chunks']:
        if ch['started_s'] > t1: continue
        yy = lanes['robot'][1]; bar(ch['started_s'], ch['finished_s'], yy, EXEC, h=34)
        n = sum(int(s['repeat']) for s in ch['segments']); labs = [f"#{ch['sequence']} · {n} cmds"]
        if ch.get('start_at_s') is not None: labs.insert(0, labs[0] + f" · holds until {ch['start_at_s']} s")
        any(label(lab, ch['started_s'], ch['finished_s'], yy) for lab in labs)
    d.text((x(1.6), (lanes['robot'][1] + 22) * S), 'gaps = robot idle, waiting for a usable reply', font=F(13), fill=INK2)
    marks = {'vacuum_attached': 'caught', 'vacuum_released': 'released in fixture', 'test_complete': 'result', 'board_sorted': 'sorted to'}
    seen, row = set(), 0
    for e in r['diagnostics']['events']:
        if (e.get('board') or e.get('board_id')) != board or e['kind'] not in marks or e['kind'] in seen or e['time_s'] > t1: continue
        seen.add(e['kind']); xx = x(e['time_s']); yy = lanes['events'][1] + (-14 if row % 2 == 0 else 14); row += 1
        text = marks[e['kind']] + (f" {e.get('status') or e.get('destination')}" if e['kind'] in ('test_complete', 'board_sorted') else '')
        d.line((xx, (yy - 12) * S, xx, (yy + 12) * S), fill=INK, width=2 * S)
        d.text((xx + 6 * S, (yy - 9) * S), f"{text} {e['time_s']:.1f} s", font=F(14, True), fill=INK)
    d.text((40 * S, 540 * S), f"{run.kind.title()}. Run: {run.source.name}. Two staggered workers; one robot lane.", font=F(13), fill=INK2)
    img.resize((W // S, H // S), Image.LANCZOS).save(out, optimize=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); run = Run(a.source); a.output.mkdir(parents=True, exist_ok=True)
    for name, start, duration, camera, label in CLIPS:
        _, gif = export_clip(a.source, name, start, duration, camera, label)
        shutil.copy(gif, a.output / f'{name}.gif')
    model_view_gif(run, a.output / 'model-view.gif')
    timeline_png(run, a.output / 'pipeline-timeline.png')
    print(json.dumps(sorted(p.name for p in a.output.iterdir())))


if __name__ == '__main__':
    main()
