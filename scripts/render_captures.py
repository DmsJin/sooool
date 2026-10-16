"""Render recorded Rhythm observations with their original variable timestamps."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
p=argparse.ArgumentParser();p.add_argument('episode',type=Path);p.add_argument('output',type=Path);p.add_argument('--ffmpeg',default='ffmpeg');a=p.parse_args()
rows=[json.loads(x)for x in(a.episode/'captures.jsonl').read_text().splitlines()]
rows.sort(key=lambda x:x['virtual_s'])
end=json.loads((a.episode/'frozen.json').read_text())['duration_s']
a.output.parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='sol-video-')as d:
 listing=Path(d)/'frames.txt';lines=[]
 for i,row in enumerate(rows):
  image=(a.episode/row['image']).resolve()
  if not image.is_relative_to(a.episode.resolve()):raise ValueError('Image path escapes episode')
  stop=rows[i+1]['virtual_s']if i+1<len(rows)else end
  duration=stop-row['virtual_s']
  if duration<=0:continue
  quoted=str(image).replace("'", "'\\''")
  lines += ["file '"+quoted+"'",'duration '+str(duration)]
 lines.append("file '"+str((a.episode/rows[-1]['image']).resolve()).replace("'", "'\\''")+"'")
 listing.write_text('\n'.join(lines)+'\n')
 subprocess.run([a.ffmpeg,'-y','-v','error','-f','concat','-safe','0','-i',str(listing),'-an','-c:v','libx264','-pix_fmt','yuv420p','-r','30','-movflags','+faststart',str(a.output)],check=True)
report={'kind':'recorded_observation_capture_sequence','not_uninterrupted_realtime_recording':True,'source_captures':len(rows),'virtual_duration_s':end,'audio':False,'model_calls':0,'summary':json.loads((a.episode/'summary.json').read_text())}
a.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(a.output)
