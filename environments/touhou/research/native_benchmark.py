"""Randomized paired native-context benchmark. Subscription only; no gameplay claims.

Each block uses byte-identical full task prompt, screenshots and output schema
for all three arms. Only native wrapper configuration changes. Future samples,
private labels and entity state are never loaded. Failed arms are retained and
never replaced by a different configuration.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import itertools
import json
import math
import os
from pathlib import Path
import random
import statistics
import time

ARMS=('default','lean','aggressive')

def digest(value):return hashlib.sha256(value).hexdigest()
def load(path):return json.loads(Path(path).read_text())
def save(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def quantile(values,q):
    if not values:return None
    values=sorted(values);index=(len(values)-1)*q;low=math.floor(index);high=math.ceil(index)
    return values[low]+(values[high]-values[low])*(index-low)
def dist(values):return {'n':len(values),'p50':quantile(values,.5),'p95':quantile(values,.95),'mean':statistics.mean(values) if values else None}


def make_blocks(dataset:Path,repeats=3,seed=20261015):
    from .policies import make_prompt
    from .wire_schema import grounded_schema,schema_hash
    if type(repeats) is not int or repeats<1:raise ValueError('Positive repeats required')
    manifest=load(dataset/'manifest.json')
    items=[(case,repeat) for case in manifest['cases'] for repeat in range(repeats)]
    rng=random.Random(seed);rng.shuffle(items)
    permutations=list(itertools.permutations(ARMS))
    orders=(permutations*math.ceil(len(items)/len(permutations)))[:len(items)];rng.shuffle(orders)
    blocks=[]
    schema=grounded_schema(1,48)
    for index,((case,repeat),order) in enumerate(zip(items,orders)):
        public=load(dataset/case['input_file'])
        if digest((dataset/case['input_file']).read_bytes())!=case['input_sha256']:raise ValueError('Public input hash drift')
        config=dict(public['config'],structured=True,pixel_controls=True,chunk_size=1,max_duration=48)
        prompt=make_prompt('tracking_dodge_adaptive',public['observation'],config,public['profile'],public.get('known_plan'))
        images=[]
        for image in case['images']:
            path=(dataset/image['file']).resolve();actual=digest(path.read_bytes())
            if actual!=image['sha256']:raise ValueError('Screenshot hash drift')
            images.append({'path':str(path),'sha256':actual,'frame':image['frame']})
        blocks.append({'id':index,'case_id':case['id'],'repeat':repeat,'order':list(order),
                       'prompt':prompt,'prompt_sha256':digest(prompt.encode()),'images':images,
                       'schema_sha256':schema_hash(schema)})
    return blocks,schema


def summarize(records):
    report={'arms':{},'paired_complete_return_differences_s':{},
            'meaning':'Latency/token/protocol benchmark only. No gold safety or accuracy labels; smaller actions are not accuracy. Grounding risks require human review and safety/damage require later full episodes or private counterfactual rollout.'}
    for arm in ARMS:
        rows=[r for r in records if r['arm']==arm]
        completed=[r for r in rows if r.get('response') is not None]
        report['arms'][arm]={'attempted':len(rows),'completed':len(completed),'failures':len(rows)-len(completed),
            'valid_contract':sum(r.get('valid_contract',False) for r in rows),
            'complete_return_s':dist([r['complete_return_s'] for r in completed]),
            'native_action_rpc_s':dist([r['response']['meta']['action_rpc_seconds'] for r in completed if 'action_rpc_seconds' in r['response']['meta']]),
            'thread_prepare_s':dist([r['response']['meta']['thread_prepare_seconds'] for r in completed if 'thread_prepare_seconds' in r['response']['meta']]),
            'image_prepare_s':dist([r['response']['meta']['image_prepare_seconds'] for r in completed if 'image_prepare_seconds' in r['response']['meta']]),
            'by_randomized_position':{str(p):dist([r['complete_return_s'] for r in completed if r['position']==p]) for p in range(3)}}
        for token in ('inputTokens','cachedInputTokens','outputTokens','reasoningOutputTokens'):
            report['arms'][arm][token]=dist([r['response']['meta']['token_usage']['total'][token] for r in completed
                if r['response']['meta'].get('token_usage') and token in r['response']['meta']['token_usage'].get('total',{})])
        usage=[r['response']['meta']['token_usage']['total'] for r in completed if r['response']['meta'].get('token_usage')]
        total_input=sum(u['inputTokens'] for u in usage)
        report['arms'][arm]['aggregate_cached_input_fraction']=sum(u.get('cachedInputTokens',0) for u in usage)/total_input if total_input else None
        report['arms'][arm]['uncachedInputTokens']=dist([r['response']['meta']['token_usage']['total']['inputTokens']-r['response']['meta']['token_usage']['total'].get('cachedInputTokens',0) for r in completed if r['response']['meta'].get('token_usage')])
    by_block={}
    for row in records:by_block.setdefault(row['block_id'],{})[row['arm']]=row
    for other in ('lean','aggressive'):
        pairs=[(b['default'],b[other]) for b in by_block.values() if 'default' in b and other in b and b['default'].get('response') is not None and b[other].get('response') is not None]
        report['paired_complete_return_differences_s'][other+'-default']=dist([b['complete_return_s']-a['complete_return_s'] for a,b in pairs])
    pairs=[(b['lean'],b['aggressive']) for b in by_block.values() if all(k in b and b[k].get('response') is not None for k in ('lean','aggressive'))]
    report['paired_complete_return_differences_s']['aggressive-lean']=dist([b['complete_return_s']-a['complete_return_s'] for a,b in pairs])
    return report


def validate_response(answer):
    from .scheduler import parse_plan
    plan=parse_plan(answer)
    if len(plan)!=1 or plan[0].duration>48:raise ValueError('Frozen single-action contract exceeded')
    value=json.loads(answer) if isinstance(answer,str) else answer
    if not isinstance(value,dict) or set(value)!= {'player','boss','aim_x','plan'}:raise ValueError('Grounded fields missing/extra')
    for key in ('player','boss'):
        point=value[key]
        if point is None and key=='player':continue
        if not isinstance(point,list) or len(point)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in point):raise ValueError('Invalid visual point')
    if type(value['aim_x']) not in (int,float) or not math.isfinite(value['aim_x']):raise ValueError('Invalid aim estimate')
    return value


def score_grounding(records, private_report):
    """Post-response private audit only; never called while constructing inputs."""
    truth=private_report['observed_ground_truth']
    result={}
    for arm in ARMS:
        points={'player_error_px':[],'player_horizontal_error_px':[],
                'boss_error_px':[],'boss_horizontal_error_px':[]}
        counts={'rows':0,'invalid_outputs':0,'present_player_reported_null':0,
                'absent_player_reported_present':0,'absent_player_reported_null':0}
        for row in [r for r in records if r['arm']==arm]:
            counts['rows']+=1
            if row['case_id'] not in truth:raise ValueError('Private coordinate label missing')
            target=truth[row['case_id']]
            try:answer=validate_response(row['response']['answer'])
            except (ValueError,KeyError,TypeError):counts['invalid_outputs']+=1;continue
            predicted=answer['player']
            if not target['player_present']:
                counts['absent_player_reported_null' if predicted is None else 'absent_player_reported_present']+=1
            elif predicted is None:counts['present_player_reported_null']+=1
            else:
                actual=target['player'];dx=predicted[0]-actual['x'];dy=predicted[1]-actual['y']
                points['player_error_px'].append(math.hypot(dx,dy));points['player_horizontal_error_px'].append(abs(dx))
            actual=target['boss'];predicted=answer['boss'];dx=predicted[0]-actual['x'];dy=predicted[1]-actual['y']
            points['boss_error_px'].append(math.hypot(dx,dy));points['boss_horizontal_error_px'].append(abs(dx))
        result[arm]={**counts,**{k:dist(v) for k,v in points.items()}}
    return {'private_posthoc_coordinate_audit':result,
            'warning':'Coordinate grounding error only; not action safety, damage, game accuracy, or episode success.'}


def client_options(arm):
    # Aggressive interface is intentionally explicit: a missing supported option
    # raises, and is logged as failure, rather than silently substituting lean.
    if arm=='default':return {'lean':False}
    if arm=='lean':return {'lean':True}
    if arm=='aggressive':return {'lean':True,'aggressive':True}
    raise ValueError('Unknown arm')


def run(dataset:Path,output:Path,suite:Path,repeats=3,workers=8,seed=20261015):
    from .subscription import SubscriptionClient
    # Fail before any model request if an aggressive runtime dependency is absent.
    from .native_envelope import AGGRESSIVE_SETTINGS
    if type(workers) is not int or not 1<=workers<=8:raise ValueError('At most8 actual calls')
    output.mkdir(parents=True,exist_ok=False)
    blocks,schema=make_blocks(dataset,repeats,seed)
    save(output/'frozen_blocks.json',{'seed':seed,'workers':workers,'schema':schema,'blocks':blocks,
         'policy_sha256':digest((Path(__file__).parent/'policies.py').read_bytes()),
         'subscription_sha256':digest((Path(__file__).parent/'subscription.py').read_bytes())})
    all_records=[]
    def lane(index):
        clients={};initialization={};local=[]
        try:
            for block in blocks[index::workers]:
                for position,arm in enumerate(block['order']):
                    directory=output/f"block_{block['id']:03d}_{arm}";directory.mkdir()
                    record={'block_id':block['id'],'case_id':block['case_id'],'repeat':block['repeat'],
                            'arm':arm,'position':position,'prompt_sha256':block['prompt_sha256'],
                            'image_sha256s':[i['sha256'] for i in block['images']],
                            'schema_sha256':block['schema_sha256'],'response':None,'valid_contract':False}
                    started=time.perf_counter()
                    try:
                        if arm not in clients and arm not in initialization:
                            init_start=time.perf_counter()
                            try:
                                clients[arm]=SubscriptionClient(suite,output/f'client_lane{index}_{arm}',schema,**client_options(arm))
                                initialization[arm]={'initialization_s':time.perf_counter()-init_start}
                            except Exception as error:
                                initialization[arm]={'initialization_error_type':type(error).__name__,'initialization_error':str(error)}
                        record['client_initialization']=initialization[arm]
                        if arm not in clients:raise RuntimeError('Native initialization failed; no fallback')
                        images=[]
                        for image in block['images']:
                            data=Path(image['path']).read_bytes()
                            if digest(data)!=image['sha256']:raise ValueError('Input changed after freeze')
                            images.append(data)
                        (directory/'prompt.txt').write_text(block['prompt'])
                        request_start=time.perf_counter()
                        response=clients[arm].act(block['prompt'],images,directory)
                        record['complete_return_s']=time.perf_counter()-request_start
                        record['response']=response
                        try:validate_response(response['answer']);record['valid_contract']=True
                        except (ValueError,KeyError,TypeError) as error:record['validation_error']=str(error)
                    except Exception as error:
                        record['error_type']=type(error).__name__;record['error']=str(error)
                        # Client protocol/auth failures close the native process.
                        # Mark this lane-arm unavailable without substituting.
                        if arm in clients:
                            clients.pop(arm).close();initialization[arm]['initialization_error']='Prior request failed; arm unavailable'
                    record['attempt_total_s']=time.perf_counter()-started
                    save(directory/'benchmark_record.json',record);local.append(record)
        finally:
            for client in clients.values():client.close()
        return local
    with ThreadPoolExecutor(max_workers=min(workers,len(blocks))) as executor:
        for records in executor.map(lane,range(min(workers,len(blocks)))):all_records.extend(records)
    save(output/'records.json',all_records);save(output/'summary.json',summarize(all_records));review(dataset,output)
    return all_records


def review(dataset,output):
    manifest=load(dataset/'manifest.json');records=load(output/'records.json');sections=[]
    for case in manifest['cases']:
        imgs=''.join('<img width="320" src="'+html.escape(os.path.relpath(dataset/i['file'],output))+'">' for i in case['images'])
        cells=[]
        for row in sorted([r for r in records if r['case_id']==case['id']],key=lambda r:(r['repeat'],r['position'])):
            text=row['response']['answer'] if row.get('response') else row.get('error','Failed')
            cells.append('<tr><td>'+html.escape(str((row['repeat'],row['position'],row['arm'])))+'</td><td>'+html.escape(str(row.get('complete_return_s')))+'</td><td><pre>'+html.escape(text)+'</pre></td></tr>')
        sections.append('<h2>'+html.escape(case['id'])+'</h2>'+imgs+'<table>'+''.join(cells)+'</table>')
    (output/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Native wrapper paired comparison</title><style>body{font:15px sans-serif}td{border:1px solid #999;padding:8px}pre{white-space:pre-wrap}table{width:100%}</style><h1>Native wrapper comparison</h1><p>Same full game prompt, images and schema; native wrapper only differs. Grounding/safety requires human visual review. This is not an accuracy or episode-success measurement.</p>'+''.join(sections))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--suite',type=Path,required=True);p.add_argument('--repeats',type=int,default=3);p.add_argument('--workers',type=int,default=8);p.add_argument('--seed',type=int,default=20261015);p.add_argument('--private-coordinates',type=Path)
    a=p.parse_args();records=run(a.dataset.resolve(),a.output.resolve(),a.suite.resolve(),a.repeats,a.workers,a.seed)
    if a.private_coordinates:
        # Only read private labels AFTER every model response has finished.
        save(a.output/'private_grounding_audit.json',score_grounding(records,load(a.private_coordinates)))

if __name__=='__main__':main()
