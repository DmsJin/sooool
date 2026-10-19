"""Broadcast-style showcase export of a retained PCBA run; never re-runs the policy.

Left: the recorded MuJoCo states rendered with a render-only scene skin
(showcase_scene.py) and a slow camera drift, plus the exact images the model
received. Right: the executing reply's summary, memory note and verbatim raw
output, with the segment being executed highlighted.
"""
import argparse
import json
import os
import subprocess
from multiprocessing import Process
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
from .scene import font
from .loop import path_at, LENGTH, SPEED, DEADLINE

W, H = 1920, 1080
MV = (24, 84, 1280, 720)            # main view x, y, w, h
PX, PW = 1328, 568                  # right panel
MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
BG = '#0b1220'; CARD = '#121b2b'; CARD2 = '#18233a'; LINE = '#24324a'
FG = '#e6ebf2'; DIM = '#8a97ab'; ACC = '#7cb8ff'; THINK = '#f6c86b'; OUT = '#86e0a8'; BAD = '#f08a7e'
RESULT = {'PASS': '#4ade80', 'FAIL': '#fb7185', 'ERROR': '#fbbf24'}
REASON = {'superseded_parent_or_sequence': 'superseded by newer reply', 'invalid_output': 'invalid output',
          'request_error': 'request error', 'start_guard_mismatch': 'start guard mismatch',
          'parent_failed': 'parent chunk failed', 'in_flight_at_stop': 'in flight at stop'}


def mono(size):
    return ImageFont.truetype(MONO, size)


class Run:
    """Everything the overlay needs, read from the run's own records."""

    def __init__(self, source):
        self.source = source = Path(source)
        self.report = r = json.loads((source / 'report.json').read_text())
        replay = json.loads((source / 'replay.json').read_text())
        self.times = np.array([f['wall_time'] for f in replay['frames']])
        self.origin = float(self.times[0])
        self.calls = {c['sequence']: c for c in r['calls']}
        self.chunks = sorted(r['chunks'], key=lambda c: c['started_s'])
        self.events = sorted(r['diagnostics']['events'], key=lambda e: e['time_s'])
        self.raw, self.answers = {}, {}
        for seq in self.calls:
            p = source / f'call-{seq:03d}' / 'model' / 'result.json'
            if p.exists():
                try:
                    self.raw[seq] = json.loads(p.read_text())['answer']
                    self.answers[seq] = json.loads(self.raw[seq])
                except (ValueError, KeyError):
                    pass
        for ch in self.chunks:
            seg_of = [i for i, s in enumerate(ch['segments']) for _ in range(int(s['repeat']))]
            ch['_seg_times'] = [(c['applied_at_sim_s'], seg_of[c['index']]) for c in ch['execution']['commands']
                                if c.get('applied_at_sim_s') is not None and c['index'] < len(seg_of)]
        self.log = []
        for c in r['calls']:
            self.log.append((c['capture_s'], f"#{c['sequence']:02d} capture + request", DIM))
            if c.get('completed_s') is None:
                continue
            if c.get('selected_s') is not None:
                self.log.append((c['selected_s'], f"#{c['sequence']:02d} reply → executing", OUT))
            else:
                why = c.get('discard_reason'); self.log.append((c['completed_s'], f"#{c['sequence']:02d} dropped: {REASON.get(why, why)}", BAD))
        for e in self.events:
            if e['kind'] == 'board_sorted':
                self.log.append((e['time_s'], f"{e['board']} sorted to {e['destination']}" + (' ✓' if e['correct'] else ' ✗'), THINK))
            elif e['kind'] == 'test_complete':
                self.log.append((e['time_s'], f"{e['board_id']} test {e['status']}", ACC))
        self.log.sort(key=lambda x: x[0])
        cfg = r['config']
        self.boards = [f'PCBA-{i + 1:03d}' for i in range(5)]
        self.kind = 'SUBSCRIPTION SIMULATION · VIRTUAL CLOCK · ' + (
            'MODELED' if cfg['latency_profile'].get('kind', '').startswith('modeled') else 'MEASURED') + ' DELAY PROFILE'
        self.cfg = cfg

    def chunk_at(self, t):
        cur = None
        for ch in self.chunks:
            if ch['started_s'] <= t:
                cur = ch
        if cur is None:
            return None, False, None
        running = t < (cur.get('finished_s') or 1e9)
        seg = None
        if running:
            for ts, s in cur['_seg_times']:
                if ts <= t:
                    seg = s
                else:
                    break
        return cur, running, seg

    def score(self, t):
        ev = [e for e in self.events if e['time_s'] <= t]
        return (len({e['board'] for e in ev if e['kind'] == 'vacuum_attached'}),
                sum(e['kind'] == 'test_complete' for e in ev),
                sum(e['kind'] == 'board_sorted' and e['correct'] for e in ev))

    def board_state(self, name, t):
        st = {'state': 'ON BELT', 'laps': 0, 'result': None, 'late': False, 'sorted': None}
        for e in self.events:
            if e['time_s'] > t:
                break
            if e.get('board', e.get('board_id')) != name:
                continue
            k = e['kind']
            if k == 'vacuum_attached': st['state'] = 'HELD'
            elif k == 'vacuum_released' and st['sorted'] is None: st['state'] = 'IN FIXTURE'
            elif k == 'test_started': st['state'] = 'TESTING'
            elif k == 'test_complete': st['result'] = e['status']; st['state'] = 'TESTED'
            elif k == 'board_sorted': st['sorted'] = e['destination']; st['state'] = 'SORTED'
            elif k == 'unpicked_lap': st['laps'] = e['laps']
            elif k == 'board_deadline_missed': st['late'] = True
        return st

    def tester_state(self, t):
        state, board, result = 'IDLE', None, None
        for e in self.events:
            if e['time_s'] > t:
                break
            k = e['kind']
            if k == 'clamp_closed': state = 'CLAMPED'
            elif k == 'test_started': state, board, result = 'TESTING', e['board'], None
            elif k == 'test_complete': state, board, result = 'RESULT', e['board_id'], e['status']
            elif k == 'clamp_open' and state != 'RESULT': state = 'IDLE'
            elif k == 'board_sorted': state, board, result = 'IDLE', None, None
        return state, board, result

    def deadline_flash(self, t):
        return any(e['kind'] == 'board_deadline_missed' and 0 <= t - e['time_s'] < 3 for e in self.events)


# ---------------------------------------------------------------- 3D rendering

def _joint_layout(model):
    import mujoco
    free, scalar = [], []
    for j in range(model.njnt):
        a = model.jnt_qposadr[j]
        if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE:
            free.append(a)
        elif model.jnt_type[j] == mujoco.mjtJoint.mjJNT_BALL:
            free.append(a - 3)
        else:
            scalar.append(a)
    return free, scalar


def interp_qpos(states, times, t_abs, free, scalar):
    i = int(np.searchsorted(times, t_abs, side='right')) - 1
    i = min(max(i, 0), len(times) - 1)
    q0 = states['qpos'][i]
    if i + 1 >= len(times) or times[i + 1] - times[i] > .5:
        return q0.copy(), i
    a = float(np.clip((t_abs - times[i]) / (times[i + 1] - times[i]), 0, 1))
    q1 = states['qpos'][i + 1]; q = q0.copy()
    q[scalar] = q0[scalar] + a * (q1[scalar] - q0[scalar])
    for adr in free:
        q[adr:adr + 3] = q0[adr:adr + 3] + a * (q1[adr:adr + 3] - q0[adr:adr + 3])
        u, v = q0[adr + 3:adr + 7], q1[adr + 3:adr + 7]
        if np.dot(u, v) < 0: v = -v
        w = u + a * (v - u); q[adr + 3:adr + 7] = w / np.linalg.norm(w)
    return q, i


class Stage:
    def __init__(self, run, workdir, size=None):
        import mujoco
        from .showcase_scene import skin_scene
        self.mj = mujoco; self.run = run
        self.w, self.h = size or (MV[2], MV[3])
        xml = skin_scene(run.source / 'scene.xml', Path(workdir) / 'art')
        self.model = m = mujoco.MjModel.from_xml_string(xml)
        m.vis.global_.offwidth, m.vis.global_.offheight = self.w, self.h
        self.data = mujoco.MjData(m)
        self.states = np.load(run.source / 'recorded-states.npz')
        self.free, self.scalar = _joint_layout(m)
        orig = mujoco.MjModel.from_xml_path(str(run.source / 'scene.xml'))
        self.light_src = orig.geom('status_light').id; self.light_dst = m.geom('status_light').id
        self.renderer = mujoco.Renderer(m, self.h, self.w)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 1
        self.stack = {c: m.material(f'stack_{c}').id for c in ('red', 'amber', 'green')}
        self.stack_rgba = {c: m.mat_rgba[i].copy() for c, i in self.stack.items()}
        self.tex = m.texture('screen_tex').id; self.tex_key = None
        self.cam = mujoco.MjvCamera(); self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE

    def _screen(self, t):
        state, board, result = self.run.tester_state(t)
        key = (state, board, result)
        if key == self.tex_key:
            return
        self.tex_key = key
        m = self.model; w, h = int(m.tex_width[self.tex]), int(m.tex_height[self.tex]); nc = int(m.tex_nchannel[self.tex])
        img = Image.new('RGB', (w, h), '#08131f'); d = ImageDraw.Draw(img)
        col = {'IDLE': '#67e8f9', 'CLAMPED': '#a78bfa', 'TESTING': '#fbbf24'}.get(state, RESULT.get(result, '#67e8f9'))
        d.rectangle((0, 0, 18, h), fill=col)
        d.text((48, 22), 'FIXTURE 02 · FUNCTIONAL TEST', font=font(34, True), fill='#9fb3c8')
        big = {'IDLE': 'READY', 'CLAMPED': 'CLAMPED', 'TESTING': f'TESTING {board}'}.get(state, f'{board}  {result}')
        d.text((48, 92), big, font=font(78, True), fill=col)
        if state == 'TESTING':
            d.rectangle((48, 206, w - 48, 222), fill='#1e2a3a'); d.rectangle((48, 206, int(w * .6), 222), fill=col)
        img = img.convert('RGBA' if nc == 4 else 'RGB')
        a = m.tex_adr[self.tex]
        m.tex_data[a:a + w * h * nc] = np.asarray(img, np.uint8).reshape(-1)
        self.renderer._gl_context.make_current()
        self.mj.mjr_uploadTexture(m, self.renderer._mjr_context, self.tex)

    def _stack(self, t):
        m = self.model; state, _, _ = self.run.tester_state(t)
        on = {'green': True, 'amber': state in ('CLAMPED', 'TESTING'), 'red': self.run.deadline_flash(t) and int(t * 3) % 2 == 0}
        for c, i in self.stack.items():
            base = self.stack_rgba[c]
            m.mat_rgba[i] = np.r_[np.minimum(base[:3] * (1.9 if on[c] else .55), 1), 1]
            m.mat_emission[i] = .9 if on[c] else 0

    def _chevrons(self, t):
        scn = self.renderer.scene; mj = self.mj
        n = 26; arm = .013
        for k in range(n):
            if scn.ngeom + 2 > scn.maxgeom:
                return
            p, tan = path_at((k * LENGTH / n + SPEED * t) % LENGTH)
            head = np.arctan2(tan[1], tan[0]); tip = np.array([*p, .8006])
            for side in (-1, 1):
                ang = head + np.pi + side * .75
                d = np.array([np.cos(ang), np.sin(ang), 0])
                c, s = np.cos(ang), np.sin(ang)
                mat = np.array([c, -s, 0, s, c, 0, 0, 0, 1], dtype=np.float64)
                g = scn.geoms[scn.ngeom]
                mj.mjv_initGeom(g, mj.mjtGeom.mjGEOM_BOX, np.array([arm / 2, .0022, .0002]),
                                tip + d * arm / 2, mat, np.array([.78, .84, .92, .9], dtype=np.float32))
                g.emission = .25; scn.ngeom += 1

    def render(self, t, camera=None):
        run, mj, m, d = self.run, self.mj, self.model, self.data
        q, i = interp_qpos(self.states, run.times, run.origin + t, self.free, self.scalar)
        d.qpos[:] = q; d.qvel[:] = 0; d.ctrl[:] = self.states['ctrl'][i]; d.eq_active[:] = self.states['eq_active'][i]
        m.geom_rgba[self.light_dst] = self.states['geom_rgba'][i][self.light_src]
        self._stack(t); self._screen(t)
        mj.mj_forward(m, d)
        cam = self.cam
        if camera:
            cam.lookat[:] = camera['lookat']; cam.distance = camera['distance']
            cam.azimuth = camera['azimuth']; cam.elevation = camera['elevation']
        else:
            cam.lookat[:] = [-.12, .04, .81]
            cam.distance = 2.08 - .06 * np.sin(2 * np.pi * t / 120)
            cam.azimuth = 127 + 9 * np.sin(2 * np.pi * t / 150)
            cam.elevation = -34 + 2.5 * np.sin(2 * np.pi * t / 95)
        self.renderer.update_scene(d, camera=cam)
        self._chevrons(t)
        return self.renderer.render()


# ---------------------------------------------------------------- overlay

def wrap(draw, text, f, width):
    words, lines, line = text.split(' '), [], ''
    for w in words:
        trial = (line + ' ' + w).strip()
        if draw.textlength(trial, font=f) <= width:
            line = trial
        else:
            if line: lines.append(line)
            while draw.textlength(w, font=f) > width:
                k = len(w)
                while k > 1 and draw.textlength(w[:k], font=f) > width: k -= 1
                lines.append(w[:k]); w = w[k:]
            line = w
    if line: lines.append(line)
    return lines


def seg_spans(text):
    out, i = [], text.find('"segments"')
    while i >= 0:
        a = text.find('{"delta_xyz_m"', i)
        if a < 0: break
        b = text.find('}', a) + 1; out.append((a, b)); i = b
    return out


class Overlay:
    def __init__(self, run):
        self.run = run; self.static_key = None; self.static = None
        self.f = {k: font(*v) for k, v in dict(
            brand=(30, True), h1=(30, True), h2=(19, True), cap=(14, True), body=(17, False), big=(25, True),
            small=(14, False), tile=(24, True), tiny=(13, False)).items()}
        self.m12 = mono(12); self.m13 = mono(13)
        self.inputs = {}

    def model_input(self, seq, idx):
        key = (seq, idx)
        if key not in self.inputs:
            p = self.run.source / f'call-{seq:03d}' / 'model' / f'image_{idx}.png'
            self.inputs[key] = Image.open(p).convert('RGB').resize((272, 204), Image.LANCZOS) if p.exists() else None
            if len(self.inputs) > 12: self.inputs.pop(next(iter(self.inputs)))
        return self.inputs[key]

    def frame(self, t, view):
        run = self.run
        ch, running, seg = run.chunk_at(t)
        nlog = sum(1 for x in run.log if x[0] <= t)
        boards = tuple(tuple(sorted(run.board_state(b, t).items())) for b in run.boards)
        key = (id(ch), running, seg, nlog, boards, run.score(t))
        if key != self.static_key:
            self.static_key = key; self.static = self.draw_static(t, ch, running, seg, boards)
        img = self.static.copy()
        img.paste(Image.fromarray(view), (MV[0], MV[1]))
        d = ImageDraw.Draw(img)
        # Main view overlays.
        d.rounded_rectangle((MV[0] + 14, MV[1] + 14, MV[0] + 330, MV[1] + 44), radius=6, fill='#0b1220')
        d.text((MV[0] + 26, MV[1] + 20), 'CELL OVERVIEW · BROADCAST CAM', font=self.f['cap'], fill=ACC)
        self.draw_clock(d, t)
        self.draw_timeline_cursor(d, t)
        return img

    def draw_clock(self, d, t):
        x1 = MV[0] + MV[2]
        d.text((x1, 24), f'{t:5.1f} s', font=self.f['h1'], fill=FG, anchor='ra')
        bx0, bx1, by = x1 - 420, x1 - 140, 40
        d.rounded_rectangle((bx0, by, bx1, by + 8), radius=4, fill=LINE)
        frac = min(t / DEADLINE, 1)
        d.rounded_rectangle((bx0, by, bx0 + max(8, (bx1 - bx0) * frac), by + 8), radius=4, fill=BAD if t > DEADLINE else ACC)
        d.text((bx0, by - 20), f'BATCH DEADLINE {DEADLINE:.0f} s', font=self.f['cap'], fill=DIM)

    TL = (616, 990, 1288)  # timeline x0, y, x1

    def tx(self, s):
        x0, _, x1 = self.TL; return x0 + (x1 - x0) * min(max(s, 0), 180) / 180

    def draw_timeline_cursor(self, d, t):
        x = self.tx(t); y = self.TL[1]
        d.line((x, y - 22, x, y + 22), fill=FG, width=2)
        d.polygon([(x - 5, y - 26), (x + 5, y - 26), (x, y - 20)], fill=FG)

    def draw_static(self, t, ch, running, seg, boards):
        run = self.run; f = self.f
        img = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(img)
        # Header.
        d.text((24, 22), 'SOOOOL', font=f['brand'], fill=ACC)
        x = 24 + d.textlength('SOOOOL', font=f['brand']) + 14
        d.text((x, 26), '|  PCBA TEST CELL  |  GPT-SOL VISUAL ACTIONS', font=f['h2'], fill=FG)
        d.text((24, 60), run.kind + ' · NOT REAL-TIME', font=f['cap'], fill=THINK)
        # Main view frame.
        d.rounded_rectangle((MV[0] - 2, MV[1] - 2, MV[0] + MV[2] + 1, MV[1] + MV[3] + 1), radius=4, outline=LINE, width=2)
        # Model input insets.
        seq = ch['sequence'] if ch else None
        c = run.calls.get(seq, {}) if seq is not None else {}
        y0 = MV[1] + MV[3] + 14
        for k, (idx, cam) in enumerate([(0, 'TOP'), (1, 'WRIST')]):
            x0 = MV[0] + k * 288
            d.rounded_rectangle((x0, y0, x0 + 276, y0 + 238), radius=6, fill=CARD)
            label = f'MODEL INPUT #{seq:02d} · {cam}' if seq is not None else f'MODEL INPUT · {cam}'
            d.text((x0 + 10, y0 + 8), label, font=f['cap'], fill=ACC)
            im = self.model_input(seq, idx) if seq is not None and (idx == 0 or 'wrist' in c.get('cameras', [])) else None
            if im is not None:
                img.paste(im, (x0 + 2, y0 + 31))
            else:
                d.text((x0 + 138, y0 + 132), 'not sent with this reply' if seq is not None else 'waiting', font=f['small'], fill=DIM, anchor='mm')
        # Board status tiles.
        bx0 = MV[0] + 2 * 288; bw = MV[0] + MV[2] - bx0
        d.rounded_rectangle((bx0, y0, bx0 + bw, y0 + 238), radius=6, fill=CARD)
        picked, tested, sorted_ok = run.score(t)
        d.text((bx0 + 12, y0 + 8), 'BATCH', font=f['cap'], fill=ACC)
        d.text((bx0 + bw - 12, y0 + 6), f'picked {picked}/5 · tested {tested}/5 · sorted correctly {sorted_ok}/5',
               font=f['small'], fill=FG, anchor='ra')
        tw = (bw - 24 - 4 * 8) / 5
        for k, (name, st) in enumerate(zip(run.boards, boards)):
            st = dict(st); x0 = bx0 + 12 + k * (tw + 8); ty = y0 + 34
            col = RESULT.get(st['sorted'] or st['result'], '#3b4b63')
            d.rounded_rectangle((x0, ty, x0 + tw, ty + 84), radius=6, fill=CARD2, outline=col if (st['sorted'] or st['result']) else None, width=2)
            d.text((x0 + 10, ty + 8), name, font=f['cap'], fill=FG)
            label = {'SORTED': f"→ {st['sorted']}", 'TESTED': f"{st['result']}", 'TESTING': 'TESTING',
                     'IN FIXTURE': 'IN FIXTURE', 'HELD': 'HELD'}.get(st['state'], 'ON BELT')
            d.text((x0 + 10, ty + 30), label, font=f['h2'], fill=RESULT.get(st['sorted'] or st['result'], FG))
            sub = f"lap {st['laps']}" if st['state'] == 'ON BELT' else (f"result {st['result']}" if st['state'] == 'HELD' and st['result'] else '')
            if st['late']: sub = (sub + ' · ' if sub else '') + 'missed deadline'
            d.text((x0 + 10, ty + 58), sub, font=f['tiny'], fill=BAD if st['late'] else DIM)
        # Timeline.
        x0, y, x1 = self.TL
        d.text((bx0 + 12, y0 + 126), 'TIMELINE  0–180 s', font=f['cap'], fill=ACC)
        d.rounded_rectangle((x0, y - 3, x1, y + 3), radius=3, fill=LINE)
        for c2 in run.chunks:
            a, b = self.tx(c2['started_s']), self.tx(c2.get('finished_s') or c2['started_s'] + .1)
            d.rectangle((a, y - 14, max(a + 1, b), y - 8), fill='#2f6f53')
        for c2 in run.report['calls']:
            if c2.get('discard_reason') and c2.get('completed_s') is not None:
                xx = self.tx(c2['completed_s']); d.line((xx, y + 8, xx, y + 14), fill=BAD, width=1)
        xd = self.tx(DEADLINE)
        for yy in range(y - 26, y + 26, 6): d.line((xd, yy, xd, yy + 3), fill=BAD, width=2)
        d.text((xd + 4, y - 40), 'deadline', font=f['tiny'], fill=BAD)
        for e in run.events:
            if e['kind'] == 'board_sorted':
                xx = self.tx(e['time_s']); col = RESULT[e['destination']]
                d.ellipse((xx - 6, y - 6, xx + 6, y + 6), fill=col)
                d.text((xx, y + 18), e['board'][-1], font=f['tiny'], fill=col, anchor='mt')
        d.text((x0, y + 28), 'green bars: chunks executing · red ticks: dropped replies · dots: boards sorted', font=f['tiny'], fill=DIM)
        # Right panel.
        self.draw_panel(d, img, t, ch, running, seg)
        d.text((24, H - 19), 'Offline render of recorded native states (poses interpolated to 20 fps) · scene dressing and belt chevrons are render-only;'
               ' model-input insets are the exact images sent · model text is verbatim output, not hidden reasoning', font=f['tiny'], fill=DIM)
        return img

    def draw_panel(self, d, img, t, ch, running, seg):
        run, f = self.run, self.f
        x0, x1 = PX, PX + PW; y = 24
        d.rounded_rectangle((x0, y, x1, H - 34), radius=10, fill=CARD)
        x0 += 22; x1 -= 22; y += 18
        d.text((x0, y), f"GPT-SOL · {run.cfg.get('model', '')} · effort {run.cfg.get('effort', '')}", font=f['cap'], fill=DIM); y += 24
        d.text((x0, y), 'Live decision', font=f['h1'], fill=FG); y += 46
        if ch is None:
            d.text((x0, y), 'Waiting for the first reply...', font=f['body'], fill=DIM); return
        seq = ch['sequence']; ans = run.answers.get(seq, {}); c = run.calls.get(seq, {})
        status = 'EXECUTING' if running else 'DONE · WAITING FOR NEXT REPLY'
        pill = f'REPLY #{seq:02d} · {status}'
        pw = d.textlength(pill, font=f['cap']) + 24
        d.rounded_rectangle((x0, y, x0 + pw, y + 26), radius=13, fill='#1f3b2c' if running else CARD2)
        d.text((x0 + 12, y + 5), pill, font=f['cap'], fill=OUT if running else DIM); y += 40
        for ln in wrap(d, ans.get('summary', c.get('summary', '')), f['big'], x1 - x0)[:3]:
            d.text((x0, y), ln, font=f['big'], fill=FG); y += 33
        y += 10
        n = sum(int(s['repeat']) for s in ch['segments'])
        tiles = [('IMAGE AGE', f"{ch['source_age_at_start_s']:.1f} s"), ('SEGMENTS', str(len(ch['segments']))),
                 ('COMMANDS', f'{n} · {n * .05:.1f} s')]
        tw = (x1 - x0 - 20) / 3
        for k, (lab, val) in enumerate(tiles):
            tx = x0 + k * (tw + 10)
            d.rounded_rectangle((tx, y, tx + tw, y + 66), radius=8, fill=CARD2)
            d.text((tx + 12, y + 9), lab, font=f['cap'], fill=DIM)
            d.text((tx + 12, y + 30), val, font=f['tile'], fill=FG)
        y += 78
        info = f"captured {c.get('capture_s', 0):.1f} s → started {ch['started_s']:.1f} s"
        if ch.get('start_at_s') is not None: info += f" · model-timed start_at {ch['start_at_s']} s"
        d.text((x0, y), info, font=f['small'], fill=DIM); y += 28
        d.text((x0, y), 'THINKING · model memory note', font=f['cap'], fill=THINK); y += 22
        for ln in wrap(d, ans.get('memory', '-'), f['body'], x1 - x0)[:4]:
            d.text((x0, y), ln, font=f['body'], fill=FG); y += 23
        y += 12
        d.text((x0, y), 'RAW OUTPUT · verbatim JSON', font=f['cap'], fill=OUT)
        d.text((x1, y), 'highlight = segment executing now', font=f['tiny'], fill=DIM, anchor='ra'); y += 22
        text = run.raw.get(seq, ''); spans = seg_spans(text)
        hl = spans[seg] if (seg is not None and seg < len(spans)) else (-1, -1)
        cw = d.textlength('M', font=self.m12); per = int((x1 - x0) // cw); lh = 15
        bottom = 880
        room = int((bottom - y) // lh)
        starts = list(range(0, len(text), per)); first = 0
        if len(starts) > room and hl[0] >= 0:
            first = max(0, min(hl[0] // per - 3, len(starts) - room))
        for k_ln, k in enumerate(starts[first:first + room]):
            piece = text[k:k + per]
            a, b = max(hl[0], k) - k, min(hl[1], k + per) - k
            if a < b: d.rectangle((x0 + a * cw, y - 1, x0 + b * cw, y + lh - 2), fill='#2c4a78')
            d.text((x0, y), piece, font=self.m12, fill='#cfe3d6'); y += lh
        if first + room < len(starts):
            d.text((x1, bottom + 2), f'… {len(starts) - first - room} more lines', font=f['tiny'], fill=DIM, anchor='ra')
        y = 900
        d.line((x0, y, x1, y), fill=LINE, width=1); y += 12
        d.text((x0, y), 'RECENT CALLS · 2 concurrent workers', font=f['cap'], fill=ACC); y += 22
        for ts, txt, col in [e for e in run.log if e[0] <= t][-5:]:
            d.text((x0, y), f'{ts:6.1f}s', font=self.m13, fill=DIM)
            d.text((x0 + 70, y - 1), txt, font=f['small'], fill=col); y += 20


# ---------------------------------------------------------------- close-up clips

def export_clip(source, name, start, duration, camera, label, fps=10, size=(960, 540), gif_width=480):
    """Close-up explainer clip (MP4 + GIF) with a step label and the executing reply's summary."""
    os.environ.setdefault('MUJOCO_GL', 'egl')
    source = Path(source).resolve(); run = Run(source); workdir = source / 'showcase'; workdir.mkdir(exist_ok=True)
    stage = Stage(run, workdir, size); w, h = size
    f_lab, f_txt, f_t = font(30, True), font(24, False), font(26, True)
    mp4 = workdir / f'clip-{name}.mp4'
    writer = imageio_ffmpeg.write_frames(str(mp4), (w, h), fps=fps, codec='libx264', pix_fmt_out='yuv420p',
                                         output_params=['-crf', '18', '-preset', 'medium'], macro_block_size=1)
    writer.send(None)
    try:
        for k in range(int(duration * fps)):
            t = start + k / fps
            img = Image.fromarray(stage.render(t, camera)); d = ImageDraw.Draw(img)
            d.rounded_rectangle((16, 14, 28 + d.textlength(label, font=f_lab), 58), radius=8, fill=BG)
            d.text((22, 18), label, font=f_lab, fill=ACC)
            d.rounded_rectangle((w - 150, 14, w - 16, 58), radius=8, fill=BG)
            d.text((w - 24, 18), f'{t:5.1f} s', font=f_t, fill=FG, anchor='ra')
            ch, running, _ = run.chunk_at(t)
            if ch is not None:
                text = run.answers.get(ch['sequence'], {}).get('summary', '')
                lines = wrap(d, f"Reply #{ch['sequence']:02d}: {text}", f_txt, w - 48)[:2]
                band = 16 + 32 * len(lines)
                d.rectangle((0, h - band, w, h), fill=BG)
                for i, ln in enumerate(lines):
                    d.text((24, h - band + 8 + 32 * i), ln, font=f_txt, fill=OUT if running else DIM)
            writer.send(np.asarray(img))
    finally:
        writer.close()
    gif = workdir / f'clip-{name}.gif'; ff = imageio_ffmpeg.get_ffmpeg_exe()
    filt = f'fps={fps},scale={gif_width}:-1:flags=lanczos'
    pal = workdir / f'clip-{name}-palette.png'
    subprocess.run([ff, '-v', 'error', '-y', '-i', str(mp4), '-vf', filt + ',palettegen=stats_mode=diff', str(pal)], check=True)
    subprocess.run([ff, '-v', 'error', '-y', '-i', str(mp4), '-i', str(pal), '-filter_complex',
                    f'[0:v]{filt}[v];[v][1:v]paletteuse=dither=sierra2_4a:diff_mode=rectangle', '-loop', '0', str(gif)], check=True)
    pal.unlink()
    return mp4, gif


# ---------------------------------------------------------------- driver

def _worker(source, out, workdir, frames, fps):
    os.environ.setdefault('MUJOCO_GL', 'egl')
    run = Run(source); stage = Stage(run, workdir); overlay = Overlay(run)
    writer = imageio_ffmpeg.write_frames(str(out), (W, H), fps=fps, codec='libx264', pix_fmt_out='yuv420p',
                                         output_params=['-crf', '19', '-preset', 'medium', '-threads', '1'], macro_block_size=1)
    writer.send(None)
    try:
        for n, k in enumerate(frames):
            t = k / fps
            writer.send(np.asarray(overlay.frame(t, stage.render(t))))
            if n % 200 == 0: print(json.dumps({'segment': out.name, 'done': n, 'of': len(frames)}), flush=True)
    finally:
        writer.close()


def export(source, output=None, fps=20, workers=2, stills=None):
    source = Path(source).resolve(); run = Run(source)
    workdir = source / 'showcase'; workdir.mkdir(exist_ok=True)
    from .showcase_art import make_showcase_art
    make_showcase_art(workdir / 'art'); (workdir / 'art' / '.done').write_text('ok\n')
    if stills:
        os.environ.setdefault('MUJOCO_GL', 'egl')
        stage = Stage(run, workdir); overlay = Overlay(run)
        for t in stills:
            overlay.frame(t, stage.render(t)).save(workdir / f'still-{t:06.1f}.png')
        return
    duration = float(run.times[-1] - run.origin) + .5
    total = int(duration * fps)
    output = Path(output) if output else source / f'showcase-{W}x{H}-{fps}fps.mp4'
    bounds = np.linspace(0, total, workers + 1).astype(int)
    parts = [workdir / f'part-{k}.mp4' for k in range(workers)]
    procs = [Process(target=_worker, args=(source, parts[k], workdir, list(range(bounds[k], bounds[k + 1])), fps)) for k in range(workers)]
    for p in procs: p.start()
    for p in procs:
        p.join()
        if p.exitcode: raise SystemExit(f'worker failed: {p.exitcode}')
    listing = workdir / 'parts.txt'; listing.write_text(''.join(f"file '{p}'\n" for p in parts))
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing),
                    '-c', 'copy', '-movflags', '+faststart', str(output)], check=True)
    for p in parts: p.unlink()
    listing.unlink()
    meta = {'path': str(output), 'width': W, 'height': H, 'fps': fps, 'frames': total, 'duration_s': total / fps,
            'interpolation': 'linear qpos / normalized quaternion between retained native states (gaps > 0.5 s held)',
            'scene': 'render-only showcase skin (showcase_scene.py); actor observations unchanged',
            'model_calls': 0, 'kind': run.kind}
    output.with_suffix('.json').write_text(json.dumps(meta, indent=2) + '\n'); print(json.dumps(meta))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True); p.add_argument('--output', type=Path)
    p.add_argument('--fps', type=int, default=20); p.add_argument('--workers', type=int, default=2)
    p.add_argument('--stills', type=float, nargs='*')
    a = p.parse_args(); export(a.source, a.output, a.fps, a.workers, a.stills)


if __name__ == '__main__':
    main()
