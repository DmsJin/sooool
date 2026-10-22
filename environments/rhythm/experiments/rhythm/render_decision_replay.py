"""Render original observation PNGs plus public action logs and labelled captions.

This edits presentation only: no game is rerun and no decisions/times are repaired.
Captions are optional retrospective summaries, never recorded chain-of-thought.
"""
import argparse
from bisect import bisect_right
import json
import statistics
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont

CJK='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
BOLD='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
MONO='/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
WHITE='#e5efff';MUTED='#8aa2c0';CYAN='#80e4ef';BG='#081221'


def load(path):return json.loads(Path(path).read_text())


def wrap(text,font,width):
    lines=[];line=''
    for char in text:
        if char=='\n' or (line and font.getlength(line+char)>width):
            lines.append(line);line='' if char=='\n' else char
        else:line+=char
    if line:lines.append(line)
    return lines


def audio_origin(diagnostics):
    stable=[d for d in diagnostics[1:] if d['state']=='playing' and not d.get('paused',False) and d['audio_s']>=.5 and d.get('rate',1)==1]
    selected=stable or diagnostics[:1]
    return statistics.median(d['external_ms']-d['audio_s']*1000 for d in selected)


def render(run_dir,captions_path,audio,output,language='zh',tail_s=0,frame_content_lag_ms=0):
    run=Path(run_dir).resolve();out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    result=load(run/'result.json')
    origin=audio_origin(result['diagnostics']);song_duration=result['args']['duration'];duration=song_duration+tail_s
    rows=[json.loads(line) for line in (run/'requests.jsonl').read_text().splitlines()]
    if captions_path:
        scenes=load(captions_path)['scenes']
    else:
        scenes=[]
        for row in rows:
            if 'commentary' not in row or not row.get('answer'):continue
            c=row['commentary'];receipt=row.get('receipt',{})
            scenes.append({'at_s':(receipt.get('clock_ms',c['received_ms'])-origin)/1000,
              'comment_s':(c['received_ms']-origin)/1000,
              'capture_s':(row['frame_metadata'][-1]['capture_end_ms']-frame_content_lag_ms-origin)/1000,
              'action_s':(receipt.get('clock_ms',c['received_ms'])-origin)/1000,
              'rtt_s':row.get('metadata',{}).get('latency_s',0),
              'answer':row['answer'],'summary':c['text'],'version':row['version'],
              'admitted':any(a['status']=='admitted' for a in receipt.get('rawacks',[]))})
        if not scenes:raise ValueError('No original live commentary in this run')
    scenes=sorted(scenes,key=lambda x:x['at_s'])
    if not captions_path:
        scenes=[s for i,s in enumerate(scenes) if i==0 or s['admitted']]
        (out/'displayed-scenes.json').write_text(json.dumps(scenes,ensure_ascii=False,indent=2))
    frames={};executed={}
    for row in rows:
        for name,metadata in zip(row['frames'],row['frame_metadata']):
            t=max(0,(metadata['capture_end_ms']-frame_content_lag_ms-origin)/1000)
            if t<duration:frames[t]=run/name
        for receipt in row.get('receipt',{}).get('rawacks',[]):
            if receipt['status']=='executed':executed[receipt['seq']]=receipt
    for receipt in result['executor']['rawacks']:
        if receipt['status']=='executed':executed[receipt['seq']]=receipt
    sensor_manifest=run/'display-frames/frames.json'
    if sensor_manifest.exists():
        frames={}
        for metadata in load(sensor_manifest):
            t=max(0,(metadata['capture_end_ms']-frame_content_lag_ms-origin)/1000)
            if t<duration:frames[t]=sensor_manifest.parent/metadata['file']
    frames=sorted(frames.items());frames[0]=(0,frames[0][1]);fts=[x[0] for x in frames]
    actions=sorted(executed.values(),key=lambda x:x['actual_ms'])
    ats=[(x['actual_ms']-origin)/1000 for x in actions]
    sts=[s['at_s'] for s in scenes]
    times=sorted({0.,*fts,*[x for x in sts if 0<=x<duration],*[s['comment_s'] for s in scenes if not captions_path and 0<=s['comment_s']<duration],*[x for x in ats if 0<=x<duration],*[min(x+.14,duration-.001) for x in ats if 0<=x<duration]})
    fonts={n:ImageFont.truetype(CJK,n,index=2) for n in [9,14,16,18,20,22,24,26]}
    bold={n:ImageFont.truetype(BOLD,n,index=2) for n in [17,24,30,34]}
    mono=ImageFont.truetype(MONO,19)
    bg=Image.new('RGB',(1440,900),BG);bd=ImageDraw.Draw(bg)
    bd.rounded_rectangle((472,28,1404,872),18,fill='#101e32',outline='#29405e',width=1)
    cache={};concat=['ffconcat version 1.0'];last_canvas=None;last_signature=None
    for index,t in enumerate(times):
        fp=frames[max(0,bisect_right(fts,t)-1)][1]
        if fp not in cache:
            original=Image.open(fp).convert('RGB');g=original.copy();gd=ImageDraw.Draw(g)
            if captions_path:
                # Explicitly documented label corrections; gameplay pixels untouched.
                for y in range(25,49):gd.line((61,y,168,y),fill=original.getpixel((176,y)))
                gd.text((64,23),'正在演奏',font=bold[17],fill='#edf5ff')
                for y in range(815,839):gd.line((170,y,330,y),fill=original.getpixel((160,y)))
                gd.text((178,819),'DFJK 击打 · 空格暂停',font=fonts[9],fill='#88a5c3')
            if len(cache)>3:cache.clear()
            cache[fp]=g
        canvas=bg.copy();canvas.paste(cache[fp],(36,28));d=ImageDraw.Draw(canvas)
        if language=='en':
            from .replay_english import EnglishDraw
            d=EnglishDraw(d)
        si=bisect_right(sts,t)-1;scene=scenes[si] if si>=0 else None
        ai=bisect_right(ats,t)-1
        signature=(si,not scene or captions_path or t>=scene['comment_s'],ai,ai>=0 and t-ats[ai]<.14)
        if last_canvas is not None and signature==last_signature:
            canvas=last_canvas.copy();canvas.paste(cache[fp],(36,28));d=ImageDraw.Draw(canvas)
            d.rectangle((1180,44,1380,102),fill='#101e32')
            d.text((1190,58),f'{min(t,song_duration):05.2f} / {song_duration:.0f}s',font=bold[24],fill=CYAN)
        else:
            d.text((500,48),'GPT 实时决策' if not captions_path else 'GPT 决策回放',font=bold[34],fill=WHITE)
            d.text((500,100),'gpt-6.1-sol  /  ultrafast  /  原速 1×  /  响应节选',font=fonts[18],fill=MUTED)
            d.text((1190,58),f'{min(t,song_duration):05.2f} / {song_duration:.0f}s',font=bold[24],fill=CYAN)
            d.line((500,139,1376,139),fill='#29405e',width=1)
            si=bisect_right(sts,t)-1;scene=scenes[si] if si>=0 else None
            if scene:
                d.text((500,154),'看到的画面',font=fonts[16],fill=MUTED)
                d.text((500,180),f'{scene["capture_s"]:05.2f}s',font=bold[30],fill=WHITE)
                d.text((790,154),'解说收到时刻' if not captions_path else '这条响应返回',font=fonts[16],fill=MUTED)
                d.text((790,180),f'{scene.get("comment_s",scene["at_s"]):05.2f}s' if captions_path or t>=scene['comment_s'] else '生成中…',font=bold[30],fill=WHITE)
                d.text((1080,154),'完整 API 响应耗时',font=fonts[16],fill=MUTED)
                d.text((1080,180),f'{scene["rtt_s"]:.2f}s',font=bold[30],fill=WHITE)
            else:
                d.text((500,171),'正在等待第一条动作响应…',font=fonts[26],fill=MUTED)
            d.text((500,244),'GPT 当场解说' if not captions_path else 'GPT 回看解说',font=bold[24],fill=CYAN)
            d.text((1200,249),'同次响应' if not captions_path else '事后生成',font=fonts[16],fill='#e7bd78')
            summary=(scene['summary'] if captions_path or t>=scene['comment_s'] else '动作已交付，正在接收同次响应的解说…') if scene else '模型读取原始截图，根据音符位置和公开时钟输出按键时间。'
            if language=='en':
                from .replay_english import translate
                summary=translate(summary)
            for i,line in enumerate(wrap(summary,fonts[24],850)[:3]):d.text((500,286+i*34),line,font=fonts[24],fill=WHITE)
            d.text((500,388),'动作先交付，解说紧随其后；文字为模型当场原文。' if not captions_path else '解说依据截图与日志生成；原始记录只有动作输出。',font=fonts[16],fill=MUTED)
            d.rounded_rectangle((498,431,1378,555),9,fill='#081322')
            d.text((500,409),'当时的原始输出',font=fonts[16],fill=MUTED)
            raw=scene['answer'] if scene else '{"a":[]}  // 尚无响应'
            lines=wrap(raw,mono,842)
            for i,line in enumerate(lines[:4]):d.text((516,449+i*25),line,font=mono,fill='#b5d7f6')
            if len(lines)>4:raise ValueError('Plan display overflow; increase panel instead of hiding commands')
            d.text((500,582),'按键',font=fonts[16],fill=MUTED)
            d.text((660,582),'模型计划的歌曲内时刻',font=fonts[16],fill=MUTED)
            d.text((1055,582),'动作交付时的余量' if not captions_path else '响应返回时的余量',font=fonts[16],fill=MUTED)
            plan=json.loads(scene['answer'])['a'] if scene else []
            for i,(_,key,at,_) in enumerate(plan[:3]):
                yy=615+i*31
                lead=(at-origin)/1000-scene['at_s']
                d.text((506,yy),key.upper(),font=bold[24],fill=CYAN)
                d.text((672,yy),f'{(at-origin)/1000:.3f}s',font=fonts[22],fill=WHITE)
                d.text((1070,yy),f'{lead*1000:+.0f} ms',font=fonts[22],fill='#f1b08e' if lead<0 else WHITE)
            if len(plan)>3:d.text((500,713),f'另有 {len(plan)-3} 条，完整内容见原始输出',font=fonts[14],fill=MUTED)
            ai=bisect_right(ats,t)-1;active=actions[ai] if ai>=0 else None
            if active:
                d.text((500,748),f'最新实际按键  {active["key"].upper()}  /  {(active["actual_ms"]-origin)/1000:.3f}s',font=fonts[20],fill=WHITE)
                d.text((500,778),f'ID {active["id"]}  ·  相对模型计划 {active["actual_ms"]-active["at_ms"]:+.1f}ms',font=fonts[16],fill=MUTED)
            else:d.text((500,748),'等待实际按键事件',font=fonts[20],fill=MUTED)
            for i,key in enumerate('dfjk'):
                x=500+i*218;lit=active and active['key']==key and t-ats[ai]<.14
                d.rounded_rectangle((x,819,x+192,857),7,fill='#38768b' if lit else '#1b304b',outline='#6099ae' if lit else '#2b4465')
                d.text((x+87,819),key.upper(),font=bold[24],fill='#efffff' if lit else MUTED)
            d.text((36,880),'实采截图拼接 · 原速 1× · 同次 API 响应的动作与简短解说' if not captions_path else '实采截图拼接 · 中文标签勘误 · 回看解说非原始推理记录',font=fonts[14],fill=MUTED)
            last_canvas=canvas.copy();last_signature=signature
        target=out/f'frame-{index:04d}.jpg';canvas.save(target,quality=92,subsampling=0)
        end=times[index+1] if index+1<len(times) else duration
        concat.extend([f"file '{target}'",'option framerate 1000000',f'duration {end-t:.9f}'])
    concat.extend([f"file '{target}'",'option framerate 1000000']);(out/'frames.ffconcat').write_text('\n'.join(concat)+'\n')
    video=out/'rhythm-original-speed-with-decisions.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(out/'frames.ffconcat'),'-i',str(Path(audio).resolve()),'-vf','fps=30','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-af','apad','-c:a','aac','-b:a','128k','-t',str(duration),'-movflags','+faststart',str(video)],check=True)
    (out/'provenance.json').write_text(json.dumps({'source_run':str(run),'audio_origin_ms':origin,'audio_origin_method':'median stable post-start audio diagnostics; startup fallback only if necessary','frame_content_lag_ms':frame_content_lag_ms,'duration_s':duration,'song_duration_s':song_duration,'language':language,'tail_s':tail_s,'speed':1,'continuous_recording':sensor_manifest.exists(),'gameplay_pixels':'Original captured PNGs, unmodified' if not captions_path else 'Original captured PNGs; only header/footer missing-glyph labels redrawn','corrected_labels':[] if not captions_path else ['正在演奏','DFJK 击打 · 空格暂停'],'decision_panel':'Original model JSON, public capture/receipt/execution clocks','captions':'Original live public explanation, same API response as action; not private chain of thought' if not captions_path else 'Retrospective subscription-generated visible evidence summaries; NOT recorded model reasoning','captions_file':str(Path(captions_path).resolve()) if captions_path else None,'audio':'Original preview remuxed, not recorded audio','frames':len(times)},ensure_ascii=False,indent=2))
    print(video)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',required=True);p.add_argument('--captions',help='Optional retrospective mode for older action-only recordings')
    p.add_argument('--language',choices=('zh','en'),default='zh');p.add_argument('--tail-seconds',type=float,default=0)
    p.add_argument('--frame-content-lag-ms',type=float,default=0,help='Presentation-only measured screenshot content age; never shifts action or receipt times')
    p.add_argument('--audio',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();render(a.run_dir,a.captions,a.audio,a.output,a.language,a.tail_seconds,a.frame_content_lag_ms)
