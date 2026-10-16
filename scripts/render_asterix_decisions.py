"""Render recorded public decision summaries with verified gameplay and optional music."""
import argparse
import bisect
import json
from pathlib import Path
import subprocess
import sys
import textwrap

from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'environments/asterix'))
from simulate_5x import make_env


def render(episode,output,ffmpeg='ffmpeg'):
    summary=json.loads((episode/'summary.json').read_text())
    steps=[json.loads(x) for x in (episode/'steps.jsonl').read_text().splitlines()]
    decisions={d['seq']:d for d in (json.loads(x) for x in (episode/'decisions.jsonl').read_text().splitlines())}
    events=json.loads((episode/'actions.json').read_text())
    if any('requested_action' not in e for e in events):raise ValueError('Selected direct-action records required')
    times=[e['frame'] for e in events]
    names=['NOOP','UP','RIGHT','LEFT','DOWN','UPRIGHT','UPLEFT','DOWNRIGHT','DOWNLEFT']
    try:
        font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',21)
        small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16)
    except OSError:
        font=ImageFont.load_default(size=21);small=ImageFont.load_default(size=16)
    env,obs,info,noops=make_env(summary['seed']);assert noops==summary['reset_noops']
    output.parent.mkdir(parents=True,exist_ok=True)
    encoder=subprocess.Popen([ffmpeg,'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1040x480','-r','12','-i','-',
        '-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],stdin=subprocess.PIPE)
    score=0.
    mode='REALTIME REPLAY' if summary.get('mode')=='realtime' else 'PROFILE SIM REPLAY'
    try:
        for frame,step in enumerate(steps):
            image=Image.new('RGB',(1040,480),'#11171f')
            image.paste(Image.fromarray(obs).resize((320,420),Image.Resampling.NEAREST),(0,60))
            draw=ImageDraw.Draw(image)
            draw.text((8,4),f'SOOOOL | {mode}',font=small,fill='#8bd2ff')
            draw.text((8,26),f'game {frame/60:.2f}s | score {int(score)} | lives {info["lives"]}',font=small,fill='white')
            draw.text((348,16),'MODEL DECISION SUMMARY',font=font,fill='#8bd2ff')
            draw.text((348,49),'One request; complete actions held until replaced',font=small,fill='#b4bec9')
            draw.text((348,88),'Executing: '+names[step['action']],font=font,fill='white')
            index=bisect.bisect_right(times,frame)-1
            if index>=0:
                event=events[index];d=decisions[event['seq']]
                assert event['action']==event['requested_action']==d['chosen']
                reason=d.get('reason') or 'Action-only condition: no public rationale requested.'
                if d.get('reason'):assert json.loads(d['answer'])['reason'].strip()==reason
                draw.text((348,128),f'Reply #{event["seq"]}: {names[d["chosen"]]}',font=font,fill='white')
                for i,line in enumerate(textwrap.wrap(reason,width=51)):
                    draw.text((348,197+i*29),line,font=font,fill='white')
                draw.text((348,373),f'Observed at {d["obs_frame"]/60:.2f}s | applied at {event["frame"]/60:.2f}s',font=small,fill='#b4bec9')
            else:draw.text((348,150),'Waiting for first model reply...',font=font,fill='white')
            draw.text((348,440),'Public summary, not private reasoning. Saved-action replay; zero model calls.',font=small,fill='#b4bec9')
            encoder.stdin.write(image.tobytes())
            obs,reward,done,truncated,info=env.step(step['action']);score+=reward
            assert step['frame']==frame and reward==step['reward'] and score==step['score'] and info['lives']==step['lives']
        assert len(steps)==summary['frames'] and score==summary['score']
    finally:
        env.close();encoder.stdin.close()
    if encoder.wait():raise RuntimeError('Video encoder failed')
    return {'source_mode':summary.get('mode','historical_profile_simulation'),'verified_frames':len(steps),'model_calls':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('episode',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--music',action='store_true');p.add_argument('--ffmpeg',default='ffmpeg');a=p.parse_args()
    plain=a.output.with_name(a.output.stem+'-plain.mp4') if a.music else a.output
    result=render(a.episode,plain,a.ffmpeg)
    if a.music:
        from polish_asterix_video import main
        main(plain.resolve(),a.output.resolve())
    a.output.with_suffix('.replay.json').write_text(json.dumps(result,indent=2)+'\n')
