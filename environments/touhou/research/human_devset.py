"""Build retrospective human visual cases; keep all future human actions private."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil


def load(path):return json.loads(path.read_text())
def rows(path):return [json.loads(line) for line in path.read_text().splitlines()]
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source, output, requested_frames):
    recorded=load(source/'manifest.json');verification=load(source/'verification.json')
    assert recorded['provider']=='human' and not recorded.get('is_smoke')
    assert recorded.get('frame_uploads_complete',True), 'Keyframe uploads are still pending'
    assert verification['verified'] and verification.get('bounded_float',True)
    frames=rows(source/'frames.jsonl');actions=rows(source/'actions.jsonl')
    output.mkdir(parents=True,exist_ok=False);(output/'cases').mkdir();(output/'private').mkdir()
    manifest={'kind':'retrospective_human_visual_devset','version':1,'split':'development',
              'source_run':source.name,'input_boundary':'Past original PNGs, observed held keys, observed frame, static control configuration and historical delay distribution only. No future human action, exact state or trajectories.',
              'cases':[]}
    review=['<!doctype html><meta charset="utf-8"><title>真人示范 · 视觉案例</title><style>body{background:#141017;color:#eedfea;font:15px system-ui;margin:25px}article{margin:30px 0;border-top:1px solid #584152}img{width:30%;max-width:360px}a{color:#d5a5d8}</style><h1>真人示范 · 六个观察时刻</h1><p>每个当前时刻保持 Z＋Shift、方向键已释放。只给模型过去约一秒的三张原图；未来真人操作另存私有标签，不能视为唯一正确动作。</p>']
    for requested in requested_frames:
        latest=next(row for row in frames if row['frame']==requested)
        assert latest['held']==[0,1,1,0],f'Not stationary focused fire at {requested}'
        past=[]
        for target in [requested-60,requested-30,requested]:
            eligible=[row for row in frames if row['frame']<=target and row['clock']['visual_frame']<=latest['clock']['visual_frame']]
            past.append(max(eligible,key=lambda row:row['clock']['visual_frame']))
        assert len({row['clock']['visual_frame'] for row in past})==3
        ident=f'human-obs-{requested:04d}';dest=output/'cases'/ident;dest.mkdir()
        images=[]
        for i,row in enumerate(past):
            original=source/row['png'];assert sha(original)==row['sha256']
            file=f'image_{i}.png';shutil.copyfile(original,dest/file)
            images.append({'file':f'cases/{ident}/{file}','frame':row['frame'],
                           'visual_frame':row['clock']['visual_frame'],'sha256':row['sha256']})
        observation={'image_frames':[row['frame'] for row in past],'held':latest['held'],
                     'clock':{'frame':latest['frame'],'visual_frame':latest['clock']['visual_frame'],
                              'intro':latest['clock']['intro'],'mode':'realtime','speed':1}}
        public={'observation':observation,'known_plan':[],
                'config':{'speed':1,'chunk_size':1,'max_duration':48,'structured':True,'pixel_controls':True},
                'profile':{'p50_s':1.8822492905019317,'p95_s':3.1355952711586657,
                           'control_age_p50_s':2.17,'control_age_p95_s':2.54}}
        save(dest/'input.json',public)
        future=[{'delta_visual_frames':row['visual_frame']-latest['clock']['visual_frame'],
                 'delta_logical_frames':row['logical_frame']-requested,'action':row['action']}
                for row in actions if latest['clock']['visual_frame']<row['visual_frame']<=latest['clock']['visual_frame']+300]
        private={'human_demonstrations':[{'source_run':source.name,'future_visual_window':300,'future_actions':future}],
                 'warning':'Private retrospective reference only. Future human actions must not enter the player prompt, and are not a unique gold action.'}
        save(output/'private'/f'{ident}.json',private)
        manifest['cases'].append({'id':ident,'source_run':source.name,'source_logical_frame':requested,
            'source_visual_frame':latest['clock']['visual_frame'],'observation_frame':requested,
            'image_logical_span':requested-past[0]['frame'],'input_file':f'cases/{ident}/input.json',
            'input_sha256':sha(dest/'input.json'),'images':images,'private_labels':f'private/{ident}.json'})
        review.append(f'<article><h2>{html.escape(ident)} · {requested/60:.2f} 游戏秒</h2><p>图帧 {[row["frame"] for row in past]} · 当前键位 [0,1,1,0]</p>')
        review.extend(f'<img src="{image["file"]}">' for image in images)
        review.append(f'<p><a href="cases/{ident}/input.json">模型可见输入</a> · <a href="private/{ident}.json">私有真人后续参考</a></p></article>')
    save(output/'manifest.json',manifest);(output/'review.html').write_text(''.join(review))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--frames',nargs='+',type=int,required=True);args=parser.parse_args()
    result=build(args.source,args.output,args.frames)
    print(json.dumps({'output':str(args.output),'cases':len(result['cases'])}))
