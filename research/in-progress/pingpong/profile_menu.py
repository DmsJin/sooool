"""Offline profiling of public-pixel candidate construction; no model calls."""
import argparse,base64,io,json,sys,time
# Existing API profile.py shares a name with the standard library profiler.
script_path=sys.path.pop(0)
import cProfile,pstats
sys.path.insert(0,script_path)
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from core.episode import load_plugin
load_plugin(str(ROOT/'sports/tabletennis/plugin.py'))
from candidates import Candidates

def run(source,spec,output):
 c=Candidates(json.loads(spec.read_text()),mode='geometry_stable_early_chunk');prof=cProfile.Profile();times=[]
 for seq in range(55,66):
  text=json.loads((source/f'decision_{seq:05d}/input.json').read_text())['params']['input'][0]['text']
  state=json.loads(text.split('\nSTATE ')[1].split('\nIMAGE_META ')[0])
  meta=json.loads(text.split('\nIMAGE_META ')[1].split('\nCANDIDATES ')[0])
  timing=json.loads(text.split('\nTIMING ')[1].split('\nSTATE ')[0])
  meta['image_png_b64']=base64.b64encode((source/'observations'/f'{seq:05d}.png').read_bytes()).decode()
  before=time.monotonic();prof.enable();opts=c.build({'state':state,'observation':meta},timing);prof.disable()
  times.append({'seq':seq,'menu_s':time.monotonic()-before,'options':len(opts)})
 stream=io.StringIO();pstats.Stats(prof,stream=stream).sort_stats('cumulative').print_stats(15)
 result=json.dumps(times)+'\n'+stream.getvalue();output.write_text(result);print(result)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--spec',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.source,a.spec,a.output)
