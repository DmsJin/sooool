"""Render retained native MuJoCo states offline; never re-run the policy."""
import argparse
import json
from pathlib import Path
import numpy as np
import mujoco
import imageio_ffmpeg
from PIL import Image,ImageDraw
from .scene import font


def export(source,width=1920,height=1440,camera='overview',duration=None,start=0.,sample_interval=.5):
    source=Path(source).resolve();states=np.load(source/'recorded-states.npz')
    replay=json.loads((source/'replay.json').read_text())
    report=json.loads((source/'report.json').read_text()) if (source/'report.json').exists() else {}
    simulated=report.get('kind')=='subscription_simulation_virtual_clock'
    if 'simulation_times_s' in replay:
        times=replay['simulation_times_s'];kind='OFFLINE ORACLE / NOT VLA EVALUATION'
    elif simulated:
        times=[f['wall_time'] for f in replay['frames']]
        profile=report['config']['latency_profile']
        kind='SUBSCRIPTION SIMULATION / VIRTUAL CLOCK / '+('MODELED' if profile.get('kind','').startswith('modeled') else 'MEASURED')+' DELAY PROFILE'
    else:
        times=[f['wall_time'] for f in replay['frames']];kind='ACTUAL MODEL RUN / CLOCK AUDIT IN REPORT'
    # Public model summaries of each executed chunk, on the same clock as the retained states.
    summaries={c['sequence']:c.get('summary','') for c in report.get('calls',[])}
    chunks=sorted((c.get('started_s',c.get('started_wall')),c['revision'],summaries.get(c['sequence'],''))
        for c in report.get('chunks',[]) if c.get('started_s',c.get('started_wall')) is not None)
    original_count=len(times)
    if not times:raise ValueError('No retained states')
    if start<0 or sample_interval<.1 or (duration is not None and duration<=0):raise ValueError('Invalid export window')
    origin=times[0];clip_start=origin+start
    clip_end=min(times[-1]+.5,clip_start+duration) if duration is not None else times[-1]+.5
    if clip_start>=clip_end:raise ValueError('Export window is outside the trial')
    first=max(0,int(np.searchsorted(times,clip_start,side='right'))-1)
    indices=[];next_sample=clip_start
    for i in range(first,len(times)):
        if times[i]>=clip_end:break
        if not indices or times[i]>=next_sample:
            indices.append(i);next_sample=max(times[i],clip_start)+sample_interval
    model=mujoco.MjModel.from_xml_path(str(source/'scene.xml'))
    model.vis.global_.offwidth=width;model.vis.global_.offheight=height
    data=mujoco.MjData(model);renderer=mujoco.Renderer(model,height=height,width=width)
    suffix=f'-first-{duration:g}s' if duration is not None else ''
    if start:suffix+=f'-from-{start:g}s'
    path=source/f'replay-{width}x{height}{suffix}.mp4'
    writer=imageio_ffmpeg.write_frames(str(path),(width,height),fps=10,codec='libx264',pix_fmt_out='yuv420p',
        output_params=['-crf','20','-preset','fast','-threads','2','-movflags','+faststart'],macro_block_size=1)
    writer.send(None);count=0
    try:
        for j,i in enumerate(indices):
            timestamp=times[i]
            for k in ('qpos','qvel','ctrl','eq_active'):getattr(data,k)[:]=states[k][i]
            model.geom_rgba[:]=states['geom_rgba'][i];data.time=float(timestamp-origin)
            mujoco.mj_forward(model,data);renderer.update_scene(data,camera=camera)
            frame=Image.fromarray(renderer.render());draw=ImageDraw.Draw(frame)
            k=height/1440;big=max(13,round(27*k));small=max(12,round(23*k));pad=max(8,round(24*k))
            active=[c for c in chunks if c[0]<=timestamp]
            lines=[(kind,font(big,True),'#93c5fd'),(f'{"Virtual" if simulated else "Trial"} elapsed {timestamp-origin:.1f}s | native replay, samples >= {sample_interval:g}s',font(small),'white')]
            if active:
                text=f'Chunk {active[-1][1]}: {active[-1][2]}';f2=font(small);cut=False
                while draw.textlength(text+('...' if cut else ''),font=f2)>width-2*pad and len(text)>4:text=text[:-1];cut=True
                lines.append((text.rstrip()+('...' if cut else ''),f2,'#fde68a'))
            band=pad+sum(round(l[1].size*1.3) for l in lines)
            draw.rectangle((0,height-band,width,height),fill='#111d2c');y=height-band+pad//2
            for text,f,color in lines:draw.text((pad,y),text,font=f,fill=color);y+=round(f.size*1.3)
            pixels=np.asarray(frame)
            end=times[indices[j+1]] if j+1<len(indices) else clip_end
            target=round((end-clip_start)*10)
            while count<target:writer.send(pixels);count+=1
            if j%30==0:print(json.dumps({'rendered':j+1,'total':len(indices)}),flush=True)
    finally:writer.close();renderer.close()
    meta={'path':str(path),'width':width,'height':height,'video_fps':10,'frames':count,'duration_s':count/10,
          'native_samples':len(indices),'retained_native_samples':original_count,'interpolation':False,
          'camera':camera,'kind':kind,'model_calls':0,'requested_duration_s':duration,'start_s':start,'export_sample_interval_s':sample_interval}
    (source/f'video-export{suffix}.json').write_text(json.dumps(meta,indent=2)+'\n');print(json.dumps(meta),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['export'])
    p.add_argument('--source',type=Path,required=True);p.add_argument('--width',type=int,default=1920)
    p.add_argument('--height',type=int,default=1440);p.add_argument('--camera',default='overview')
    p.add_argument('--duration',type=float)
    p.add_argument('--start',type=float,default=0.);p.add_argument('--sample-interval',type=float,default=.5)
    a=p.parse_args();export(a.source,a.width,a.height,a.camera,a.duration,a.start,a.sample_interval)
