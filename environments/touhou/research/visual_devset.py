"""Small retrospective visual devset. Single-step comparisons are not wins.

Build copies original screenshots unchanged. Player input is constructed from
an explicit public metadata allowlist, never labels or sampled current delay.
Private labels support later human demonstrations; no one action is a gold key.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
import math
import os
from pathlib import Path
import random
import shutil


def digest(data):return hashlib.sha256(data).hexdigest()
def load(path):return json.loads(Path(path).read_text())
def save(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def rows(path):return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def public_metadata(row,config,profile):
    """Audit whitelist. In particular exclude state, source actions and delay_frames."""
    clock={k:row.get('capture_clock',{}).get(k) for k in
           ('frame','visual_frame','intro','mode','speed','wall_ms') if k in row.get('capture_clock',{})}
    return {'observation':{'image_frames':row['image_frames'],'held':row.get('held',[0,0,0,0]),'clock':clock},
            'config':{'speed':config.get('speed',1),'chunk_size':1,'max_duration':48,
                      'structured':True,'pixel_controls':True},
            'profile':{k:profile[k] for k in ('p50_s','p95_s','control_age_p50_s','control_age_p95_s') if k in profile}}


def build(root:Path,spec:list[dict],output:Path,delay_profile:dict | None = None):
    output.mkdir(parents=True,exist_ok=False)
    (output/'cases').mkdir();(output/'private').mkdir()
    manifest={'kind':'retrospective_visual_single_step_devset','version':1,'cases':[],
              'split':'development','not_episode_success_metric':True,'input_boundary':'Original PNGs plus allowlisted observed held/clock and historical delay summaries. No private labels, engine state, future trajectories or sampled current delay.'}
    for item in spec:
        case_id=item['id']
        if not case_id.replace('-','').replace('_','').isalnum():raise ValueError('Unsafe case id')
        episode=root/item['episode'];seq=item['seq'];directory=episode/f'decision_{seq:05d}'
        row=next(r for r in rows(episode/'issued.jsonl') if r['seq']==seq)
        config=load(episode/'config.json')
        profile=delay_profile if delay_profile is not None else load(Path(config['profile']))
        public=public_metadata(row,config,profile)
        # Retain only the already-returned schedule from the original visible
        # prompt, never its policy prose, future answer, or sampled latency.
        public['known_plan']=[]
        source_prompt=directory/'prompt.txt'
        if source_prompt.exists():
            for line in source_prompt.read_text().splitlines():
                if line.startswith('Known returned plan: '):
                    public['known_plan']=json.loads(line[len('Known returned plan: '):].removesuffix('.'))
        dest=output/'cases'/case_id;dest.mkdir()
        images=[]
        paths=sorted(directory.glob('image_*.png'))
        if len(paths)!=len(row['image_frames']):raise ValueError('Screenshot count mismatch')
        for index,path in enumerate(paths):
            data=path.read_bytes()
            expected=row.get('image_sha256',[])
            if expected and digest(data)!=expected[index]:raise ValueError('Source screenshot hash mismatch')
            name=f'image_{index}.png';(dest/name).write_bytes(data)
            images.append({'file':f'cases/{case_id}/{name}','frame':row['image_frames'][index],'sha256':digest(data)})
        save(dest/'input.json',public)
        source_decision=next((r for r in rows(episode/'decisions.jsonl') if r['seq']==seq),{})
        private={'rubric':item.get('rubric',[]),'coverage_tags':item.get('tags',[]),
                 'source_executed_or_proposed_action_for_audit_only':source_decision.get('plan'),
                 'human_demonstrations':[],
                 'warning':'Historical action is not a gold label. Multiple safe tracking/dodge actions may be correct.'}
        save(output/'private'/f'{case_id}.json',private)
        manifest['cases'].append({'id':case_id,'source_episode':str(episode),'source_seq':seq,
            'source_logical_frame':row['logical_frame'],'source_visual_frame':row['visual_frame'],
            'issued_sha256':digest((episode/'issued.jsonl').read_bytes()),
            'input_file':f'cases/{case_id}/input.json','input_sha256':digest((dest/'input.json').read_bytes()),
            'images':images,'private_labels':f'private/{case_id}.json'})
    save(output/'manifest.json',manifest)
    return manifest


def metrics(answer):
    from .scheduler import parse_plan
    try:
        plan=parse_plan(answer)
        if len(plan)!=1 or plan[0].duration>48:raise ValueError('Frozen one-action48-frame contract exceeded')
    except (ValueError,TypeError,KeyError) as error:
        return {'valid_contract':False,'error':str(error)}
    a=plan[0]
    horizontal=a.move in (2,3,4,6,7,8)
    displacement=a.duration*(1.6 if a.focus else 3.44)*(1/math.sqrt(2) if a.move in (2,4,6,8) else 1) if horizontal else 0
    return {'valid_contract':True,'shoot':bool(a.shoot),'focus':bool(a.focus),'bomb':bool(a.bomb),
            'stationary':a.move==0,'duration_frames':a.duration,'planned_horizontal_displacement_px':displacement,
            'focused_small_nudge':bool(horizontal and a.focus and displacement<=35),
            'warning':'These are descriptive action measures, not safety/correctness scores. Grounding, delayed threat and gap quality require visual human review or private counterfactual rollout.'}


def compare(dataset:Path,output:Path,suite:Path,candidates:list[str],repeats=2,workers=12,limit=6,envelope='lean'):
    from .policies import make_prompt
    from .subscription import SubscriptionClient
    from .wire_schema import grounded_schema
    if not 1<=workers<=12 or repeats<1:raise ValueError('Require1..12workers and positive repeats')
    if envelope not in ('default','lean','aggressive'):raise ValueError('Unknown native envelope')
    output.mkdir(parents=True,exist_ok=False)
    manifest=load(dataset/'manifest.json')
    cases=manifest['cases'][:limit]
    tasks=[(c,v,r) for c in cases for v in candidates for r in range(repeats)]
    random.Random(719).shuffle(tasks)
    results=[]
    # One process per worker, at most12simultaneous requests. Each response gets
    # a new ephemeral thread; source episode, rubric and variant names withheld.
    def lane(index):
        client=SubscriptionClient(suite,output/f'client_{index}',grounded_schema(1,48),
                                  lean=envelope=='lean',aggressive=envelope=='aggressive')
        local=[]
        try:
            for position in range(index,len(tasks),workers):
                case,candidate,repeat=tasks[position]
                public=load(dataset/case['input_file'])
                for entry in case['images']:
                    if digest((dataset/entry['file']).read_bytes())!=entry['sha256']:raise ValueError('Image hash drift')
                if digest((dataset/case['input_file']).read_bytes())!=case['input_sha256']:raise ValueError('Input hash drift')
                prompt=make_prompt(candidate,public['observation'],public['config'],public['profile'],public.get('known_plan'))
                call=output/f'call_{position:03d}'
                call.mkdir();(call/'prompt.txt').write_text(prompt)
                response=client.act(prompt,[(dataset/i['file']).read_bytes() for i in case['images']],call)
                record={'case_id':case['id'],'candidate':candidate,'repeat':repeat,'call':call.name,
                        'prompt_sha256':digest(prompt.encode()),'response':response,'metrics':metrics(response['answer'])}
                save(call/'comparison.json',record);local.append(record)
        finally:client.close()
        return local
    with ThreadPoolExecutor(max_workers=min(workers,len(tasks))) as executor:
        for completed in executor.map(lane,range(min(workers,len(tasks)))):results.extend(completed)
    save(output/'results.json',{'mode':'subscription_blind_single_step','not_episode_win':True,
         'model':'gpt-6.1-sol','effort':'low','repeats':repeats,'workers':workers,
         'candidates':candidates,'envelope':envelope,'results':results,
         'human_review_axes':['Newest-frame player and boss grounding','Focused tracking magnitude without overshoot','Threat prediction over historical control delay','Clear-gap route across entire maneuver','Standing still when appropriate; do not force one gold action']})
    review(dataset,output)
    return results


def review(dataset,output):
    manifest=load(dataset/'manifest.json')
    result=load(output/'results.json') if (output/'results.json').exists() else {'results':[]}
    esc=lambda x:html.escape(str(x))
    sections=[]
    for case in manifest['cases']:
        public=load(dataset/case['input_file'])
        imgs=''.join('<img width="320" src="'+esc(os.path.relpath(dataset/i['file'],output))+'">' for i in case['images'])
        records=[r for r in result['results'] if r['case_id']==case['id']]
        cells=''.join('<tr><td>'+esc(r['candidate'])+' / '+esc(r['repeat'])+'</td><td><pre>'+esc(r['response']['answer'])+'</pre></td><td>'+esc(r['metrics'])+'</td></tr>' for r in sorted(records,key=lambda x:(x['candidate'],x['repeat'])))
        private_path=dataset/case['private_labels']
        labels=load(private_path) if private_path.exists() else {'warning':'Private labels remain on the local review machine; none were uploaded to the player environment.'}
        source=case.get('source_episode',case.get('source_run','unknown'))
        rubric=labels.get('rubric',labels.get('warning','No unique gold action.'))
        sections.append('<article><h2>'+esc(case['id'])+'</h2><p>'+esc(source)+' seq '+esc(case.get('source_seq','human'))+' frame '+esc(case['source_logical_frame'])+'</p>'+imgs+'<p>Historical delay: '+esc(public['profile'])+'</p><p>Human rubric (withheld from models): '+esc(rubric)+'</p><table>'+cells+'</table></article>')
    (output/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Touhou visual cases</title><style>body{font:15px sans-serif;background:#eee;color:#222;margin:24px}article{background:white;padding:18px;margin-bottom:24px}table{border-collapse:collapse;width:100%}td{border:1px solid #aaa;padding:8px}pre{white-space:pre-wrap;max-width:500px}img{image-rendering:pixelated}</style><h1>Touhou visual devset</h1><p>Retrospective single-step decisions. This is not episode success. Descriptive action metrics are not correctness scores; judge delayed threats and clear paths from chronological screenshots. Private labels are shown here only for human review.</p>'+''.join(sections))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build');b.add_argument('--root',type=Path,required=True);b.add_argument('--spec',type=Path,required=True);b.add_argument('--output',type=Path,required=True);b.add_argument('--delay-profile',type=Path)
    c=sub.add_parser('compare');c.add_argument('--dataset',type=Path,required=True);c.add_argument('--output',type=Path,required=True);c.add_argument('--suite',type=Path,required=True);c.add_argument('--candidates',nargs='+',required=True);c.add_argument('--repeats',type=int,default=2);c.add_argument('--workers',type=int,default=12);c.add_argument('--limit',type=int,default=6);c.add_argument('--envelope',choices=['default','lean','aggressive'],default='lean')
    r=sub.add_parser('review');r.add_argument('--dataset',type=Path,required=True);r.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.command=='build':build(a.root,load(a.spec),a.output,load(a.delay_profile) if a.delay_profile else None);review(a.output,a.output)
    elif a.command=='compare':compare(a.dataset,a.output,a.suite,a.candidates,a.repeats,a.workers,a.limit,a.envelope)
    else:review(a.dataset,a.output)


if __name__=='__main__':main()
