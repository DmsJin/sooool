"""Add an original quiet arcade soundtrack and brighten only the game region."""
import argparse
import json
from pathlib import Path
import subprocess
import wave

import numpy as np


def soundtrack(path,seconds):
    rate=22050
    audio=np.zeros(round(seconds*rate),dtype=np.float64)
    rng=np.random.default_rng(28)
    beat=60/112
    chords=[(60,64,67),(57,60,64),(53,57,60),(55,59,62)]
    phrases=[(76,79,81,79,76,74,72,74),(76,72,69,72,76,79,76,72),
             (77,76,72,69,72,76,77,76),(74,79,78,79,74,71,74,79)]
    def note(start,duration,midi,gain,bright=False):
        a=round(start*rate);n=min(round(duration*rate),len(audio)-a)
        if n<=0:return
        t=np.arange(n)/rate
        hz=440*2**((midi-69)/12)
        signal=np.sin(2*np.pi*hz*t)
        if bright:signal+=.14*np.sin(2*np.pi*hz*2*t)+.05*np.sin(2*np.pi*hz*3*t)
        env=np.minimum(t/.008,1)*np.minimum((duration-t)/.055,1)*np.exp(-t*2.4)
        audio[a:a+n]+=gain*signal*np.maximum(env,0)
    for k in range(int(seconds/beat)+1):
        chord=chords[(k//4)%4]
        note(k*beat,beat*.8,chord[0]-24,.095)
        for sub in (0,1):
            start=(k+sub*.5)*beat
            note(start,beat*.42,chord[(k*2+sub)%3]+12,.032)
            # Alternate melody registers and leave a little space each fourth bar.
            if not (k%16>=14 and sub==1):
                melody=phrases[(k//4)%4][(k%4)*2+sub]
                note(start,beat*.43,melody-(12 if (k//16)%2 else 0),.060,True)
            a=round(start*rate);n=min(round(.045*rate),len(audio)-a)
            if n>0:
                noise=rng.normal(size=n)
                noise=np.diff(noise,prepend=noise[0])
                audio[a:a+n]+=.004*noise*np.exp(-np.arange(n)/(rate*.012))
    fade=np.minimum(np.arange(len(audio))/(rate*1.5),1)*np.minimum((len(audio)-np.arange(len(audio)))/(rate*2.5),1)
    audio=np.clip(audio*fade,-.95,.95)
    with wave.open(str(path),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate)
        f.writeframes((audio*32767).astype('<i2').tobytes())


def main(source,output):
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(source)]))
    duration=float(info['format']['duration'])
    output.parent.mkdir(parents=True,exist_ok=True)
    music=output.with_suffix('.music.wav')
    soundtrack(music,duration)
    filters=('[0:v]split=2[base][game];'
        '[game]crop=320:420:0:60,eq=brightness=0.025:contrast=1.10:saturation=1.30:gamma=1.07[bright];'
        '[base][bright]overlay=0:60[v];'
        '[1:a]loudnorm=I=-24:TP=-3:LRA=7[a]')
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-i',str(music),
        '-filter_complex',filters,'-map','[v]','-map','[a]','-c:v','libx264','-crf','18',
        '-preset','veryfast','-c:a','aac','-b:a','128k','-t',str(duration),'-movflags','+faststart',str(output)],check=True)
    output.with_suffix('.json').write_text(json.dumps({'source':str(source),'duration_seconds':duration,
        'music':'Original procedural arcade composition; generated locally, no external recording.',
        'audio_loudness_lufs':-24,'visual_edit_region':[0,60,320,420],
        'visual_edit':'brightness +0.025, contrast 1.10, saturation 1.30, gamma 1.07',
        'gameplay_actions_changed':False,'reason_text_changed':False,'new_model_calls':0},indent=2)+'\n')
    print(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();main(a.source.resolve(),a.output.resolve())
