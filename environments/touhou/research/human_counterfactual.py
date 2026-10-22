"""Private fixed-window evaluation of completed answers on human prefixes.

No model requests. Human future controls are used only for the separately
labelled undelayed reference; they are never used after a Sol handoff.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from .counterfactual_devset import load, rows, save, advance, observed_truth, estimate_error
from .environment import BrowserEnv
from .scheduler import parse_plan
from .state_compare import compare_engine_state


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_human(env, seed, actions, target):
    # Batch transport only: use exactly the existing public research methods,
    # preserving every actual frame/edge and every cinematic simulation step.
    return env.page.evaluate('''({seed,actions,target})=>{
        research.setHuman(false);research.reset(seed,'sim',1);research.setHuman(true);
        function advance(to){let c=research.getClock();
            if(to<c.visual_frame)throw new Error('Cannot reverse replay');
            while(c.visual_frame<to&&c.status==='playing'){
                const old=c.visual_frame;c=research.step(Math.min(10000,to-old));
                if(c.visual_frame===old)break;
            }return c;}
        for(const row of actions){if(row.visual_frame>target)break;
            const c=advance(row.visual_frame);
            if(c.frame!==row.logical_frame)throw new Error('Human action frame mismatch');
            research.setHumanAction(row.action);
        }advance(target);return research.diagnostics();
    }''', {'seed':seed,'actions':actions,'target':target})


def metrics(observed, before, after):
    obs, pre, post = observed['state'], before['state'], after['state']
    return dict(pre_action_hits=pre['hits']-obs['hits'],
        post_action_hits=post['hits']-pre['hits'],
        pre_action_damage=obs['boss']['hp']-pre['boss']['hp'],
        damage=pre['boss']['hp']-post['boss']['hp'],
        lives_before_action=pre['player']['lives'], lives_after=post['player']['lives'],
        pre_action_bombcost=obs['player']['bombs']-pre['player']['bombs'],
        bombcost=pre['player']['bombs']-post['player']['bombs'],
        status_before_action=pre['status'], status_after=post['status'],
        action_visual_frame=before['clock']['visual_frame'],
        end_visual_frame=after['clock']['visual_frame'],
        actual_post_action_visual_frames=after['clock']['visual_frame']-before['clock']['visual_frame'])


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8796/game/')
    parser.add_argument('--delays', nargs='+', type=float, default=[2.17, 2.54])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or args.root/'private-human-counterfactual.json'
    manifest = load(args.dataset/'manifest.json')
    source_manifest = load(args.source/'manifest.json')
    assert source_manifest['provider']=='human' and not source_manifest.get('is_smoke')
    assert manifest['source_run']==args.source.name
    actions = rows(args.source/'actions.jsonl')
    expected = load(args.source/'final_state.json')
    comparisons = [load(p) for p in sorted((args.root/'comparison').glob('call_*/comparison.json'))]
    report = dict(kind='private_human_prefix_counterfactual', private_only=True,
        not_episode_success_metric=True, delay_assumption_s=args.delays,
        post_action_window_visual_frames=120,
        source_run=str(args.source), public_input_audit=load(args.root/'comparison/public_input_audit.json'),
        input_boundary='Already completed answers only; no state, human future labels or trajectories transmitted to a model.',
        prefix_rule='Replay actual human prefix through observed visual frame; disable human input; replace with observed held keys for one logical frame, then retain Z/Shift only. Suppress all future human actions.',
        observed_ground_truth={}, rollouts=[], undelayed_human_reference=[])
    started = time.monotonic()
    with BrowserEnv(args.url) as env:
        mapping = env.page.evaluate('''()=>{const shell=document.querySelector('.game-shell'),s=shell.getBoundingClientRect(),r=document.querySelector('#game').getBoundingClientRect(),scale=640/shell.clientWidth;return {ax:(r.left-s.left-shell.clientLeft)*scale,ay:(r.top-s.top-shell.clientTop)*scale,sx:r.width*scale/480,sy:r.height*scale/640}}''')
        final = replay_human(env, source_manifest['seed'], actions, expected['clock']['visual_frame'])
        comparison = compare_engine_state(final['state'], expected['state'])
        report['source_verification'] = comparison
        save(output, report)
        assert comparison['bounded_float'], 'Full human replay differs beyond bounded floats; abort scoring'
        print(json.dumps({'source_verified':True,'max_abs_difference':comparison['max_abs_float_difference']}), flush=True)
        cases = {c['id']:c for c in manifest['cases']}
        inputs = {}
        for case in manifest['cases']:
            public = load(args.dataset/case['input_file']); inputs[case['id']]=public
            assert sha(args.dataset/case['input_file'])==case['input_sha256']
            assert public['observation']['held']==[0,1,1,0]
            observed = replay_human(env, source_manifest['seed'], actions, case['source_visual_frame'])
            assert observed['state']['tick']==case['source_logical_frame']
            report['observed_ground_truth'][case['id']]=observed_truth(observed,mapping)
        save(output, report)
        for delay in args.delays:
            for answer in comparisons:
                case=cases[answer['case_id']]
                expected_images=[image['sha256'] for image in case['images']]
                assert answer['response']['meta']['image_sha256s']==expected_images
                observed=replay_human(env,source_manifest['seed'],actions,case['source_visual_frame'])
                held=inputs[case['id']]['observation']['held']
                env.page.evaluate('research.setHuman(false)')
                env.apply([held+[1]])
                before=advance(env,case['source_visual_frame']+math.ceil(delay*60))
                eligible=before['state']['status']=='playing'
                plan=parse_plan(answer['response']['answer'])
                if eligible:
                    env.apply([a.keys+[a.duration] for a in plan])
                    after=advance(env,before['clock']['visual_frame']+120)
                else:
                    after=before
                result=dict(call=answer['call'],case_id=case['id'],candidate=answer['candidate'],repeat=answer['repeat'],
                    delay_s=delay,delay_visual_frames=math.ceil(delay*60),eligible_for_action=eligible,
                    grounding=estimate_error(answer['response']['answer'],report['observed_ground_truth'][case['id']]),
                    **metrics(observed,before,after))
                report['rollouts'].append(result); report['elapsed_s']=time.monotonic()-started
                save(output,report)
                if len(report['rollouts'])%6==0:
                    print(json.dumps({'rollouts':len(report['rollouts']),'elapsed_s':report['elapsed_s']}),flush=True)
            for case in manifest['cases']:
                observed=replay_human(env,source_manifest['seed'],actions,case['source_visual_frame'])
                before=replay_human(env,source_manifest['seed'],actions,case['source_visual_frame']+math.ceil(delay*60))
                after=replay_human(env,source_manifest['seed'],actions,before['clock']['visual_frame']+120)
                report['undelayed_human_reference'].append(dict(case_id=case['id'],delay_window_s=delay,
                    warning='Human actual future controls with no imposed delay. Different condition; not a fair latency-matched strategy comparison or unique action gold.',
                    **metrics(observed,before,after)))
                save(output,report)
    report['elapsed_s']=time.monotonic()-started;report['complete']=True;save(output,report)
    print(json.dumps({'complete':True,'rollouts':len(report['rollouts']),'output':str(output),'elapsed_s':report['elapsed_s']}),flush=True)


if __name__=='__main__':
    main()
