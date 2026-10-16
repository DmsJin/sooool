"""Replay logged model actions to inspect a failure; no inference or action policy."""
import argparse
from collections import deque, defaultdict
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw
from hop_controller_v3 import HopControllerV3
from run_realtime_hop import suffix
from simulate_5x import make_env, png, select_images


def main(args):
    root=args.episode
    meta=json.loads((root/('summary.json' if (root/'summary.json').exists() else 'progress.json')).read_text())
    n=meta['frames'];assert max(args.frames)<n
    steps=[json.loads(x) for x in (root/'steps.jsonl').read_text().splitlines()[:n]]
    issued=[]
    for line in (root/'issued.jsonl').read_text().splitlines():
        try:r=json.loads(line)
        except json.JSONDecodeError:break
        if r['obs_frame']<=max(args.frames):issued.append(r)
    by_frame={r['obs_frame']:r for r in issued};ready=defaultdict(list)
    for r in issued:
        path=root/f"call-{r['seq']:05d}"/'result.json'
        if path.exists():
            r.update(json.loads(path.read_text()))
            ready[r['action_ready_frame']].append(r)
    env,obs,info,_=make_env(meta['seed']);controller=HopControllerV3();window=deque(maxlen=9)
    args.output.mkdir(parents=True,exist_ok=False)
    panels=[];records=[];score=0.
    try:
        for f in range(max(args.frames)+1):
            action=controller.advance(f,ready[f]);assert action==steps[f]['action'],f
            if f%4==0:window.append((f,png(obs)))
            images=select_images(window)
            if f in by_frame:
                r=by_frame[f]
                assert r['held_action']==action
                assert r['image_sha256']==[hashlib.sha256(im).hexdigest() for _,im in images],f
            if f in args.frames:
                r=by_frame.get(f,{})
                panel=Image.new('RGB',(240,360),'#111111')
                panel.paste(Image.fromarray(obs).resize((240,315),Image.Resampling.NEAREST),(0,45))
                d=ImageDraw.Draw(panel)
                d.text((3,2),f"frame {f} | score {int(score)} | lives {info['lives']}",fill='white')
                d.text((3,17),f"held {action} | reply {r.get('chosen')} due {r.get('action_ready_frame')}",fill='white')
                panels.append(panel)
                record={'frame':f,'held_action':action,'score':score,'lives':info['lives'],
                        'original_chosen':r.get('chosen'),'original_due_frame':r.get('action_ready_frame'),
                        'model_images':[]}
                if f in by_frame:
                    record['prompt']=(root.parent/'prompt.txt').read_text()+suffix(f,images,action,controller.applied)
                    for t,im in images:
                        path=args.output/f'obs-{t:04d}.png';path.write_bytes(im)
                        record['model_images'].append({'frame':t,'path':str(path),'sha256':hashlib.sha256(im).hexdigest()})
                records.append(record)
            obs,reward,done,truncated,info=env.step(action);score+=reward
            assert reward==steps[f]['reward'] and score==steps[f]['score'] and info['lives']==steps[f]['lives'],f
    finally:env.close()
    canvas=Image.new('RGB',(960,360*((len(panels)+3)//4)),'#111111')
    for j,panel in enumerate(panels):canvas.paste(panel,((j%4)*240,(j//4)*360))
    canvas.save(args.output/'contact.png')
    (args.output/'observations.json').write_text(json.dumps({'verification_model_calls':0,'observations':records,
        'note':'Replayed causal observations; original answers remain separate from prompts. No target detection or prescribed new actions.'},indent=2)+'\n')
    print(json.dumps({'observations':len(records),'output':str(args.output),'model_calls':0}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--episode',type=Path,required=True)
    p.add_argument('--frames',type=int,nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
