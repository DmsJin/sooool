"""Procedural art for the render-only PCBA showcase skin (original, no third-party assets).

These textures dress offline replay exports only. Actor cameras keep the plain
research scene, so changing this file never changes what a policy observes.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from .scene import font

YELLOW = '#f5c518'


def _noise(size, scale, seed, lo, hi):
    rng = np.random.default_rng(seed)
    small = rng.random((max(2, size[1] // scale), max(2, size[0] // scale)))
    img = Image.fromarray((small * 255).astype(np.uint8)).resize(size, Image.BICUBIC)
    a = np.asarray(img, dtype=np.float32) / 255
    return lo + (hi - lo) * a


def epoxy_floor(path, n=2048):
    """Dark sealed concrete with faint mottling, saw-cut joints and a few scuffs."""
    base = np.array([44, 50, 58], np.float32)
    mott = _noise((n, n), 64, 1, -9, 9) + _noise((n, n), 9, 2, -4, 4) + _noise((n, n), 2, 3, -3, 3)
    a = np.clip(base[None, None, :] + mott[..., None], 0, 255).astype(np.uint8)
    img = Image.fromarray(a); d = ImageDraw.Draw(img)
    for k in range(0, n, n // 4):
        d.line([(k, 0), (k, n)], fill=(30, 34, 40), width=5)
        d.line([(0, k), (n, k)], fill=(30, 34, 40), width=5)
    rng = np.random.default_rng(4)
    for _ in range(40):
        x, y = rng.integers(0, n, 2); L = int(rng.integers(40, 220)); ang = rng.random() * np.pi
        d.line([(x, y), (x + L * np.cos(ang), y + L * np.sin(ang))], fill=(56, 62, 70), width=2)
    img.filter(ImageFilter.GaussianBlur(.6)).save(path)


def esd_mat(path, n=1024):
    """Grey-blue anti-static bench mat with a fine grounding grid."""
    a = np.zeros((n, n, 3), np.float32) + np.array([58, 72, 88])
    a += _noise((n, n), 3, 5, -5, 5)[..., None]
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(img)
    for k in range(0, n, 32):
        d.line([(k, 0), (k, n)], fill=(66, 82, 100), width=1)
        d.line([(0, k), (n, k)], fill=(66, 82, 100), width=1)
    img.save(path)


def brushed(path, rgb, n=512, seed=6):
    a = np.zeros((n, n, 3), np.float32) + np.array(rgb)
    rng = np.random.default_rng(seed)
    streak = rng.normal(0, 7, (n, 1)).repeat(n, 1)
    streak = np.asarray(Image.fromarray(np.uint8(np.clip(streak + 128, 0, 255))).filter(ImageFilter.GaussianBlur((0, 1))), np.float32) - 128
    a += streak[..., None] + rng.normal(0, 2, (n, n, 1))
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(path)


def belt_rubber(path, n=512):
    """Modular belt: dark polymer links with hinge lines across the travel direction."""
    a = np.zeros((n, n, 3), np.float32) + np.array([28, 31, 36])
    a += _noise((n, n), 2, 7, -4, 4)[..., None]
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(img)
    for k in range(0, n, 32):
        d.rectangle((k, 0, k + 3, n), fill=(17, 19, 23))
        d.rectangle((k + 4, 0, k + 5, n), fill=(44, 48, 55))
    img.save(path)


def wall_panels(path, w=2048, h=1024):
    """Insulated sandwich panels with seams, a kick plate and a lit clerestory band."""
    a = np.zeros((h, w, 3), np.float32) + np.array([70, 78, 90])
    a += np.linspace(16, -18, h)[:, None, None]
    a += _noise((w, h), 5, 8, -3, 3)[..., None]
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(img)
    for x in range(0, w, 256):
        d.rectangle((x, 0, x + 4, h), fill=(48, 54, 63))
        d.rectangle((x + 5, 0, x + 6, h), fill=(92, 100, 112))
    d.rectangle((0, 70, w, 190), fill=(26, 32, 40))
    for x in range(0, w, 256):
        d.rectangle((x + 16, 82, x + 240, 178), fill=(150, 175, 205))
        d.rectangle((x + 16, 128, x + 240, 132), fill=(110, 130, 155))
    d.rectangle((0, h - 120, w, h), fill=(38, 44, 52))
    d.rectangle((0, h - 128, w, h - 120), fill=(200, 160, 20))
    img.save(path)


def hazard(path, w=512, h=64):
    img = Image.new('RGB', (w, h), (18, 18, 18)); d = ImageDraw.Draw(img)
    for x in range(-h, w + h, 64):
        d.polygon([(x, h), (x + 32, h), (x + 32 + h, 0), (x + h, 0)], fill=YELLOW)
    img.save(path)


def sign(path, title, subtitle, accent, icon=None, w=1024, h=512):
    img = Image.new('RGB', (w, h), '#f4f5f7'); d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w, 150), fill=accent)
    d.text((48, 30), title, font=font(84, True), fill='white')
    y = 200
    for line in subtitle.split('\n'):
        d.text((50, y), line, font=font(54, True), fill='#1f2933'); y += 80
    if icon == 'esd':
        cx, cy, r = w - 150, 330, 110
        d.polygon([(cx, cy - r), (cx + r, cy + r * .8), (cx - r, cy + r * .8)], outline='#1f2933', width=14)
        d.line([(cx - 25, cy - 20), (cx + 20, cy + 15), (cx - 15, cy + 25), (cx + 30, cy + 70)], fill='#1f2933', width=12)
    img.save(path)


def pcb(path, index, w=1100, h=750):
    """Two-layer PCBA look: solder mask, traces, vias, pads and silkscreen.

    The USB marking stays at the same texture corner as the research scene so
    orientation cues match the plain scene that the policy saw.
    """
    rng = np.random.default_rng(100 + index)
    a = np.zeros((h, w, 3), np.float32) + np.array([10, 92, 62])
    a += _noise((w, h), 40, 200 + index, -6, 6)[..., None]
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(img)
    trace = (24, 122, 84)
    for _ in range(90):
        x, y = rng.integers([40, 40], [w - 40, h - 40]); dx, dy = rng.integers(-180, 180, 2)
        pts = [(int(x), int(y)), (int(x + dx), int(y)), (int(x + dx), int(y + dy))]
        d.line(pts, fill=trace, width=int(rng.choice([3, 4, 6])))
        for p in (pts[0], pts[-1]):
            d.ellipse((p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6), fill=(196, 170, 96))
            d.ellipse((p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2), fill=(12, 40, 30))
    for _ in range(60):
        x, y = rng.integers([30, 30], [w - 30, h - 30]); d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(196, 170, 96))
    # Silkscreen outlines roughly under the 3D components (chip, regulator, MCU).
    silk = (235, 240, 236)
    for (x0, y0, x1, y1, ref) in [(180, 170, 430, 420, 'U1'), (640, 210, 800, 390, 'U2'), (870, 420, 980, 600, 'U3')]:
        d.rectangle((x0, y0, x1, y1), outline=silk, width=4)
        d.ellipse((x0 + 10, y0 + 10, x0 + 26, y0 + 26), fill=silk)
        d.text((x0, y0 - 40), ref, font=font(30, True), fill=silk)
    for k in range(6):
        x = 150 + k * 120; d.rectangle((x, 560, x + 60, 590), outline=silk, width=3)
        d.text((x + 4, 600), f'R{k + 1}', font=font(22), fill=silk)
    for x, y in [(40, 40), (w - 40, 40), (40, h - 40), (w - 40, h - 40)]:
        d.ellipse((x - 24, y - 24, x + 24, y + 24), fill=(214, 186, 104))
        d.ellipse((x - 12, y - 12, x + 12, y + 12), fill=(16, 26, 30))
    d.rounded_rectangle((300, 470, 820, 545), radius=8, fill=(240, 244, 240))
    d.text((330, 482), f'PCBA-{index + 1:03d}  REV C', font=font(42, True), fill=(16, 60, 44))
    d.text((820, 70), 'USB', font=font(34, True), fill=silk)
    # Gold edge fingers on the left edge.
    for k in range(10):
        y = 200 + k * 34; d.rectangle((0, y, 26, y + 22), fill=(222, 182, 82))
    img.save(path)


def make_showcase_art(directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    epoxy_floor(directory / 'floor.png')
    esd_mat(directory / 'esd.png')
    brushed(directory / 'steel.png', (120, 128, 138))
    brushed(directory / 'steel_dark.png', (54, 60, 68), seed=9)
    belt_rubber(directory / 'belt.png')
    wall_panels(directory / 'wall.png')
    hazard(directory / 'hazard.png')
    sign(directory / 'sign_cell.png', 'CELL 01', 'PCBA FUNCTIONAL TEST\nPICK · TEST · SORT', '#1d4ed8')
    sign(directory / 'sign_esd.png', 'ESD AREA', 'GROUNDING REQUIRED\nBEYOND THIS POINT', '#b45309', icon='esd')
    sign(directory / 'sign_robot.png', 'CAUTION', 'AUTOMATED ROBOT\nKEEP CLEAR', '#b91c1c')
    for i in range(5):
        pcb(directory / f'board{i}.png', i)
    return directory
