"""Record real frontend observations using legal fixed keys; zero model calls."""
import argparse,json,pathlib
from .environment import BrowserEnv
from .policies import make_prompt


def main():
 p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--output',type=pathlib.Path,required=True);args=p.parse_args()
 args.output.mkdir(parents=True,exist_ok=False)
 images=[]
 with BrowserEnv(args.url) as env:
  env.reset(seed=2);env.apply([[0,1,1,0,48]])
  for target in [450,465,480]:
   env.advance_to(target);ob=env.capture();name=f'frame{ob["frame"]}.png';(args.output/name).write_bytes(ob['png']);images.append((name,ob))
  groups=[]
  for n in (1,3):
   selected=images[-n:];ob=selected[-1][1];ob['image_frames']=[x[1]['frame'] for x in selected]
   prompt=make_prompt('baseline',ob,{'chunk_size':1,'max_duration':48,'speed':1},{'p50_s':0,'p95_s':0})
   prompt=prompt.replace('Measured unloaded API complete-action delay: median 0.000s, P95 0.000s wall time. This is a distribution, not the known delay of this request.','This is a latency calibration request. The API response delay is not known yet; still choose a legal useful action from the screenshots.')
   prompt+='Use duration_frames from exactly 6,12,24,48.\n'
   groups.append({'name':f'native{n}_baseline','prompt':prompt,'images':[x[0] for x in selected]})
  (args.output/'fixtures.json').write_text(json.dumps({'fixtures':groups},indent=2))
  (args.output/'manifest.json').write_text(json.dumps({'source':'original browser rendering','model_calls':0,'images':[{'file':name,'frame':ob['frame']} for name,ob in images]},indent=2))
 print(args.output/'fixtures.json')

if __name__=='__main__':main()
