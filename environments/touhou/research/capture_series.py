"""Changing-game-image fixtures; avoids repeated-image-only cache calibration."""
import argparse,json,pathlib
from collections import deque
from .environment import BrowserEnv
from .policies import make_prompt


def main():
 p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--count',type=int,default=20);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 fixtures=[];window=deque(maxlen=3)
 with BrowserEnv(args.url) as env:
  env.reset(2);env.apply([[0,1,1,0,48]])
  for index in range(args.count+2):
   env.advance_to(420+index*15);ob=env.capture();name=f'frame{ob["frame"]}.png';(args.output/name).write_bytes(ob['png']);window.append((name,ob))
   if len(window)<3:continue
   for n in (1,3):
    selected=list(window)[-n:];o={**selected[-1][1],'image_frames':[x[1]['frame'] for x in selected]}
    prompt=make_prompt('baseline',o,{'chunk_size':1,'max_duration':48,'speed':1},{'p50_s':0,'p95_s':0}).replace('Measured unloaded API complete-action delay: median 0.000s, P95 0.000s wall time. This is a distribution, not the known delay of this request.','This is a latency calibration request. API delay is not known yet; choose a useful legal action from the screenshots.')
    prompt+='Use duration_frames from exactly 6,12,24,48.\n'
    fixtures.append({'name':f'native{n}_changing','prompt':prompt,'images':[x[0] for x in selected]})
 (args.output/'fixtures.json').write_text(json.dumps({'fixtures':fixtures},indent=2));print('Changing fixtures',len(fixtures))

if __name__=='__main__':main()
