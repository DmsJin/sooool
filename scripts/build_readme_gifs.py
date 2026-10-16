"""Rebuild README highlights from the local source paths in the manifest. No model calls."""
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/gameplay'

def build(item):
    source = Path(item['source'])
    name = item['game']
    filt = f"fps={item['fps']},"
    if item.get('crop'):
        filt += 'crop=' + item['crop'] + ','
    filt += f"scale={item['width']}:-2:flags=lanczos"
    cmd = ['ffmpeg', '-v', 'error', '-y', '-ss', str(item['start_seconds']),
           '-t', str(item['duration_seconds']), '-i', str(source)]
    palette = OUT / (name + '-palette.png')
    subprocess.run(cmd + ['-vf', filt + ',palettegen=stats_mode=diff', '-frames:v', '1', str(palette)], check=True)
    target = OUT / (name + '.gif')
    subprocess.run(cmd + ['-i', str(palette), '-filter_complex',
                         f'[0:v]{filt}[v];[v][1:v]paletteuse=dither=sierra2_4a:diff_mode=rectangle',
                         '-loop', '0', str(target)], check=True)
    palette.unlink()
    # A compact full-colour companion for manual playback and sharing.
    subprocess.run(cmd + ['-vf', filt, '-an', '-c:v', 'libx264', '-crf', '20',
                         '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(OUT / (name + '.mp4'))], check=True)
    item.update(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                gif_sha256=hashlib.sha256(target.read_bytes()).hexdigest(), bytes=target.stat().st_size)
    print(name, target.stat().st_size, flush=True)
    return item

if __name__ == '__main__':
    manifest_path = OUT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    with ThreadPoolExecutor(max_workers=4) as pool:
        manifest['clips'] = list(pool.map(build, manifest['clips']))
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
