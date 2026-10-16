"""Render and verify actual applied actions; no model calls or invented decisions."""
import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.cli import serve

def rows(p):return [json.loads(x)for x in p.read_text().splitlines()]

def encode(out,size,fps,ffmpeg):
    return subprocess.Popen([ffmpeg,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',size,'-r',str(fps),'-i','-',
        '-an','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],stdin=subprocess.PIPE)

def asterix(root,out,ffmpeg):
    from PIL import Image,ImageDraw
    sys.path.insert(0,str(ROOT/'environments/asterix'));from simulate_5x import make_env
    summary=json.loads((root/'summary.json').read_text());steps=rows(root/'steps.jsonl')
    env,obs,info,noops=make_env(summary['seed']);assert noops==summary['reset_noops']
    encoder=encode(out,'320x460',12,ffmpeg);score=0
    try:
        for frame,step in enumerate(steps):
            image=Image.new('RGB',(320,460),'#111722');image.paste(Image.fromarray(obs).resize((320,420),Image.Resampling.NEAREST),(0,40))
            ImageDraw.Draw(image).text((6,5),f'SIM 5x | game {frame/60:.2f}s | score {int(score)}\nseed {summary["seed"]} | lives {info.get("lives")}',fill='white')
            encoder.stdin.write(image.tobytes());obs,reward,done,truncated,info=env.step(step['action']);score+=reward
            assert step['frame']==frame and reward==step['reward']and score==step['score']and info.get('lives')==step['lives']
        assert score==summary['score']and len(steps)==summary['frames']
    finally:env.close();encoder.stdin.close()
    if encoder.wait():raise RuntimeError('Encoder failed')
    return {'kind':'verified_applied_action_replay','game':'asterix','fps':12,'slowdown':5,'frames':len(steps),'summary':summary,'model_calls':0}

def touhou(root,out,ffmpeg):
    from PIL import Image
    sys.path.insert(0,str(ROOT/'environments/touhou'));from research.environment import BrowserEnv
    summary=json.loads((root/'summary.json').read_text());actions=[r for r in rows(root/'actions.jsonl')if r.get('status','applied')=='applied']
    with serve(ROOT/'environments/touhou/dist')as url:
        with BrowserEnv(url)as env:
            env.reset(seed=summary['seed'],mode='sim',speed=1);visual=0;cursor=0;count=0
            first=Image.open(io.BytesIO(env.capture()['png'])).convert('RGB');encoder=encode(out,f'{first.width}x{first.height}',15,ffmpeg)
            try:
                while True:
                    while cursor<len(actions)and actions[cursor]['visual_frame']==visual:
                        env.apply(actions[cursor]['plan']);cursor+=1
                    if visual%4==0:
                        image=Image.open(io.BytesIO(env.capture()['png'])).convert('RGB');encoder.stdin.write(image.tobytes());count+=1
                    if visual==summary['visual_frames']:break
                    target=min(summary['visual_frames'],visual+(4-visual%4))
                    if cursor<len(actions):target=min(target,actions[cursor]['visual_frame'])
                    assert target>visual;env.advance(target-visual);visual=target
                expected=json.loads((root/'final_state.json').read_text());expected.pop('clock',None)
                assert env.diagnostics()['state']==expected,'Replay final state differs'
            finally:encoder.stdin.close()
            if encoder.wait():raise RuntimeError('Encoder failed')
    return {'kind':'verified_applied_action_replay','game':'touhou','fps':15,'speed':1,'frames':count,'summary':summary,'model_calls':0}

p=argparse.ArgumentParser();p.add_argument('game',choices=['asterix','touhou']);p.add_argument('episode',type=Path);p.add_argument('output',type=Path);p.add_argument('--ffmpeg',default='ffmpeg');a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
r=globals()[a.game](a.episode,a.output,a.ffmpeg);a.output.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
