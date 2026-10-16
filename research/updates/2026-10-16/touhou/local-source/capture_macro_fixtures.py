"""Build varying actual-image fixtures for grounded macro output calibration."""
import argparse,json,pathlib,re
from .environment import BrowserEnv
from .policies import make_prompt


def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--url',default='http://127.0.0.1:18791');p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 profile=json.loads((a.root/'profile-game-v1.json').read_text());config={'candidate':'grounded_macro','chunk_size':3,'max_duration':48,'speed':1,'wait_for_move':True};fixtures=[]
 with BrowserEnv(a.url) as env:
  env.reset(2)
  for visual in [0,45,90]:
   env.advance(visual-env.clock()['visual_frame']);o=env.capture();name=f'intro-{visual}.png';(a.output/name).write_bytes(o['png']);o['image_frames']=[o['frame']]
   fixtures.append({'name':'macro_intro','prompt':make_prompt('grounded_macro',o,config,profile),'images':[name]})
 for seed in [2,5,6]:
  episode=a.root/'serial-grounded-v1'/f'serial-grounded-seed{seed}';count=0
  for d in sorted(episode.glob('decision_*')):
   images=sorted(d.glob('image_*.png'))
   if len(images)!=3:continue
   row=json.loads((d/'request.json').read_text());old=(d/'prompt.txt').read_text();m=re.search(r'Known returned plan: (.*)\.\n',old);plan=json.loads(m.group(1)) if m else None
   obs={'image_frames':row['image_frames'],'held':row['held'],'clock':{'intro':0}}
   fixtures.append({'name':'macro3_changing','prompt':make_prompt('grounded_macro',obs,config,profile,plan),'images':[str(p.resolve()) for p in images]})
   count+=1
   if count==6:break
 (a.output/'fixtures.json').write_text(json.dumps({'fixtures':fixtures},indent=2));print('Fixtures',len(fixtures))

if __name__=='__main__':main()
