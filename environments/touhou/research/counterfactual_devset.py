"""Private offline fixed-window scoring. Never constructs a model request."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import time

from .environment import BrowserEnv
from .scheduler import parse_plan
from .state_compare import compare_engine_state


def load(path):return json.loads(Path(path).read_text())
def rows(path):return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def save(path, data):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,indent=2,allow_nan=False));temporary.replace(path)


def advance(env, target):
    current=env.clock()['visual_frame']
    assert target>=current
    while current<target:
        clock=env.advance(min(10000,target-current));new=clock['visual_frame']
        if new==current or clock['status']!='playing':break
        current=new
    return env.diagnostics()


def replay(env, source, target=None, capture_wall=None):
    env.reset(source['summary']['seed'])
    final=source['summary']['visual_frames'] if target is None else target
    for action in source['actions']:
        at=action['visual_frame']
        if at>final:break
        if at==final and capture_wall is not None and action.get('apply_clock',{}).get('wall_ms',-1)>capture_wall:break
        state=advance(env,at)
        assert state['clock']['frame']==action['logical_frame']
        env.apply(action['plan'])
    return advance(env,final)


def observed_truth(state, mapping):
    game=state['state'];p=game['player'];b=game['boss'];present=p['dying']==0
    point=lambda obj:{'x':mapping['ax']+mapping['sx']*obj['x'],'y':mapping['ay']+mapping['sy']*obj['y']}
    return {'source_logical_frame':game['tick'],'source_visual_frame':state['clock']['visual_frame'],
            'player_present':present,'player':point(p) if present else None,'boss':point(b),
            'player_alpha':(.3 if p['inv']>0 and (game['tick']//4)%2==0 else 1) if present else 0,
            'mapping':mapping,'private_only':True}


def estimate_error(answer, truth):
    value=json.loads(answer);p=value.get('player');b=value.get('boss')
    distance=lambda estimate,point:math.hypot(estimate[0]-point['x'],estimate[1]-point['y'])
    return {'player_presence_correct':(p is not None)==truth['player_present'],
            'player_pixel_error':distance(p,truth['player']) if p is not None and truth['player_present'] else None,
            'boss_pixel_error':distance(b,truth['boss']) if b is not None else None}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('--url',default='http://127.0.0.1:18791')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--source-root',type=Path,help='Local source-log mirror; original manifest provenance remains unchanged')
    parser.add_argument('--delays',nargs='+',type=float,default=[2.17,2.54])
    args=parser.parse_args();output=args.output or args.root/'private-counterfactual-report.json'
    manifest=load(args.root/'dataset/manifest.json');comparisons=[load(p) for p in sorted((args.root/'comparison').glob('call_*/comparison.json'))]
    source_paths=sorted({case['source_episode'] for case in manifest['cases']});sources={}
    report={'kind':'private_local_counterfactual_scores','not_episode_success_metric':True,
            'input_boundary':'No state, labels, or future source decisions were sent to any model; scoring uses already-completed answers only.',
            'delay_assumption_s':args.delays,'post_action_window_visual_frames':120,
            'prefix_rule':'Only actual applied actions through capture time; retain current plan remaining suffix. Unknown future source actions suppressed.',
            'source_verification':{},'observed_ground_truth':{},'rollouts':[]}
    started=time.monotonic()
    with BrowserEnv(args.url) as env:
        mapping=env.page.evaluate('''()=>{const shell=document.querySelector('.game-shell'),s=shell.getBoundingClientRect(),r=document.querySelector('#game').getBoundingClientRect(),scale=640/shell.clientWidth;return {ax:(r.left-s.left-shell.clientLeft)*scale,ay:(r.top-s.top-shell.clientTop)*scale,sx:r.width*scale/480,sy:r.height*scale/640}}''')
        for path in source_paths:
            directory=(args.source_root/Path(path).relative_to('/home/ubuntu/wzh/touhou-sol-study')) if args.source_root is not None else Path(path)
            source={'summary':load(directory/'summary.json'),'actions':rows(directory/'actions.jsonl'),'expected':load(directory/'final_state.json'),'issued':rows(directory/'issued.jsonl')}
            sources[path]=source;final=replay(env,source)
            expected={key:value for key,value in source['expected'].items() if key!='clock'}
            comparison=compare_engine_state(final['state'],expected)
            assert comparison['bounded_float'], f'Full source replay mismatch: {path}: {comparison}'
            report['source_verification'][path]={'exact_state_match':comparison['exact'],'bounded_float_state_match':comparison['bounded_float'],'state_comparison':comparison,'local_log_directory':str(directory),'tick':final['state']['tick'],'status':final['state']['status'],'boss_hp':final['state']['boss']['hp']}
            save(output,report);print(json.dumps({'source_verified':path}),flush=True)
        for case in manifest['cases']:
            source=sources[case['source_episode']];issued=next(r for r in source['issued'] if r['seq']==case['source_seq']);wall=issued.get('capture_clock',{}).get('wall_ms')
            observed=replay(env,source,case['source_visual_frame'],wall)
            assert observed['state']['tick']==case['source_logical_frame']
            report['observed_ground_truth'][case['id']]=observed_truth(observed,mapping)
        save(output,report);print(json.dumps({'ground_truth_cases':len(report['observed_ground_truth'])}),flush=True)
        cases={case['id']:case for case in manifest['cases']}
        for delay in args.delays:
            for comparison in comparisons:
                case=cases[comparison['case_id']];source=sources[case['source_episode']]
                issued=next(r for r in source['issued'] if r['seq']==case['source_seq']);wall=issued.get('capture_clock',{}).get('wall_ms')
                observed=replay(env,source,case['source_visual_frame'],wall);obs=observed['state']
                before=advance(env,case['source_visual_frame']+math.ceil(delay*60));pre=before['state']
                answer=comparison['response']['answer'];plan=parse_plan(answer)
                eligible=pre['status']=='playing'
                if eligible:
                    env.apply([a.keys+[a.duration] for a in plan])
                    after=advance(env,before['clock']['visual_frame']+120)
                else:after=before
                post=after['state']
                result={'call':comparison['call'],'case_id':case['id'],'candidate':comparison['candidate'],'repeat':comparison['repeat'],
                        'delay_s':delay,'delay_visual_frames':math.ceil(delay*60),'eligible_for_action':eligible,
                        'pre_action_hits':pre['hits']-obs['hits'],'post_action_hits':post['hits']-pre['hits'],
                        'pre_action_damage':obs['boss']['hp']-pre['boss']['hp'],'damage':pre['boss']['hp']-post['boss']['hp'],
                        'lives_before_action':pre['player']['lives'],'lives_after':post['player']['lives'],
                        'pre_action_bombcost':obs['player']['bombs']-pre['player']['bombs'],'bombcost':pre['player']['bombs']-post['player']['bombs'],
                        'status_before_action':pre['status'],'status_after':post['status'],
                        'action_visual_frame':before['clock']['visual_frame'],'end_visual_frame':after['clock']['visual_frame'],
                        'actual_post_action_visual_frames':after['clock']['visual_frame']-before['clock']['visual_frame'],
                        'grounding':estimate_error(answer,report['observed_ground_truth'][case['id']])}
                report['rollouts'].append(result);report['elapsed_s']=time.monotonic()-started;save(output,report)
                if len(report['rollouts'])%6==0:print(json.dumps({'rollouts':len(report['rollouts']),'elapsed_s':report['elapsed_s']}),flush=True)
    print(json.dumps({'complete':True,'rollouts':len(report['rollouts']),'output':str(output),'elapsed_s':time.monotonic()-started}),flush=True)


if __name__=='__main__':main()
