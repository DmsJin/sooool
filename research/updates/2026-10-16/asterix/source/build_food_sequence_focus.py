"""Extract causal frozen observations around a missed follow-up pickup; no action policy."""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
from run_realtime_hop import suffix
from simulate_5x import make_env, png, select_images, base_prompt
import base64


def build(args):
    prefix=[json.loads(x) for x in (args.episode/'steps.jsonl').read_text().splitlines()]
    continuation=[json.loads(x) for x in (args.continuation/'steps.jsonl').read_text().splitlines()]
    start=continuation[0]['frame']
    steps=prefix[:start]+continuation
    actions=json.loads((args.continuation/'actions.json').read_text())
    frames=args.focus_frames or [472,480,488,500,504,508]
    ids=args.focus_ids or ['C15a','C15b','C16a','C16b','C17a','C17b']
    assert len(frames)==len(ids) and len(set(frames))==len(frames) and len(set(ids))==len(ids)
    assert frames and min(frames)>=start and max(frames)<=steps[-1]['frame']
    selected=dict(zip(frames,ids));window=deque(maxlen=9)
    env,obs,info,_=make_env(5);tasks=[];metadata=[]
    delays=json.loads(args.profile.read_text())['capture_to_complete_seconds']
    try:
        for step in steps:
            f=step['frame']
            if f%4==0:window.append((f,png(obs)))
            if f in selected:
                images=select_images(window)
                history=[a for a in actions if a['frame']<=f]
                for strategy in args.strategy:
                    path=Path(strategy)
                    prompt=base_prompt(path.read_text(),delays,1.,'v3')+suffix(f,images,step['action'],history)
                    for repeat in range(3):
                        tasks.append({'variant':path.stem,'case_id':selected[f],'repeat':repeat,
                            'wrapper_profile':'minimal','prompt':prompt,
                            'pair_id':selected[f]+'-'+str(repeat),
                            'images':['data:image/png;base64,'+base64.b64encode(im).decode() for _,im in images]})
                metadata.append({'case_id':selected[f],'frame':f,'held_action':step['action'],
                    'image_frames':[t for t,_ in images],
                    'image_sha256':[hashlib.sha256(im).hexdigest() for _,im in images],
                    'note':'Diagnostic frozen state, no ground-truth or forced action supplied to model.'})
            obs,reward,_,_,info=env.step(step['action'])
            assert reward==step['reward'] and info['lives']==step['lives'],f
            if f>=max(frames):break
    finally:env.close()
    args.output.mkdir(exist_ok=False)
    (args.output/'tasks.json').write_text(json.dumps(tasks))
    (args.output/'cases.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({'tasks':len(tasks),'cases':len(metadata),'paid_api_calls':0}))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('episode','continuation','profile','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--strategy',nargs='+',required=True)
    p.add_argument('--focus-frames',type=int,nargs='+')
    p.add_argument('--focus-ids',nargs='+')
    build(p.parse_args())
