"""Private tracking scores from exact original-engine replays; no model client."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

from .counterfactual_devset import load, rows, save, replay, advance
from .human_counterfactual import replay_human
from .environment import BrowserEnv
from .scheduler import parse_plan
from .state_compare import compare_engine_state

HORIZON = 180
WARMUP = 60
DELAYS = [2.69135, 3.170205]
ENGINE_SHA256='348e81340d4a09f8b488193daf0b4e395afa2755d34f249585ff5e1ffe787aa4'

# State is private to this offline evaluator. No actor import or request path.
TRACE_JS = '''({ticks,actions,stopVisual})=>{
 const out=[];let cursor=0;
 // Offline diagnostics never capture pixels. Suppress only raster operations in
 // this private browser while advancing; restore all methods before returning.
 const proto=CanvasRenderingContext2D.prototype, saved={};
 for(const key of ['drawImage','fillRect','clearRect','stroke','fill','fillText','strokeText']){saved[key]=proto[key];proto[key]=()=>{};}
 try {
 let initial=research.diagnostics(),last=initial;
 while(last.state.status==='playing' && (ticks===null || last.state.tick-initial.state.tick<ticks)){
   if(stopVisual!==null && last.clock.visual_frame>=stopVisual)break;
   while(cursor<actions.length && actions[cursor].visual_frame<last.clock.visual_frame)cursor++;
   while(cursor<actions.length && actions[cursor].visual_frame===last.clock.visual_frame){
     const a=actions[cursor++];
     if(a.logical_frame!==last.state.tick)throw new Error('Replay action logical frame mismatch');
     research.apply(a.plan);
   }
   const before=research.diagnostics();research.step(1);const after=research.diagnostics();
   if(after.clock.visual_frame===before.clock.visual_frame)throw new Error('Replay stalled');
   if(after.state.tick!==before.state.tick){
     const p=before.state.player,q=after.state.player,b=after.state.boss;
     const orbs=after.state.events.filter(e=>e.type==='orb_hit').length;
     const score=after.state.score-before.state.score;
     const graze=after.state.graze-before.state.graze;
     const shotHits=(score-25*graze-60*orbs)/10;
     if(!Number.isInteger(shotHits)||shotHits<0)throw new Error('Unaccounted score event');
     out.push({tick:after.state.tick,visual_frame:after.clock.visual_frame,
       player_x:q.x,player_y:q.y,boss_x:b.x,boss_y:b.y,
       player_dx:q.x-p.x,held:before.clock.held,alive:before.state.player.dying===0,
       shot_hits:shotHits,bomb_orb_hits:orbs,hp_loss:before.state.boss.hp-b.hp,
       hits:after.state.hits-before.state.hits,
       bombs_used:after.state.events.filter(e=>e.type==='bomb').length,
       net_bombs_used:p.bombs-q.bombs,bombs_gained:Math.max(0,q.bombs-p.bombs),
       lives_before:p.lives,lives_after:q.lives,deaths:after.state.events.filter(e=>e.type==='crash').length,respawn:after.state.events.some(e=>e.type==='respawn'),
       cutin_visual_before:after.clock.visual_frame-before.clock.visual_frame-1});
   }
   last=after;
 }
 return {frames:out,initial,final:last};
 } finally {for(const [key,value] of Object.entries(saved))proto[key]=value;}
}'''


def trace(env, ticks=None, actions=None, stop_visual=None):
    return env.page.evaluate(TRACE_JS, dict(ticks=ticks, actions=actions or [], stopVisual=stop_visual))


def longest_run(values):
    best = current = 0
    for value in values:
        current = current+1 if value else 0
        best = max(best, current)
    return best


def score_trace(frames, *, observed_boss_x=None, warmup=WARMUP):
    """Primary reward is shot-only damage, without safety/resource conflation.

    Full-window shot damage is primary; steady damage is a secondary diagnostic.
    Nominal shot damage uses exact score decomposition, including lethal overkill;
    boss HP loss is separately clamped by the engine. Warmup prevents old in-flight
    shots dominating credit. No-shot/dead ticks break a miss run; cutins add no tick.
    """
    assessed = frames[warmup:]
    eligible = lambda f: f['alive'] and bool(f['held'][1])
    shot_hits = sum(f['shot_hits'] for f in assessed)
    # Fixed 180-tick denominator for cases, actual span for longer episode clips.
    denominator=max(HORIZON,len(frames))
    full_hits=sum(f['shot_hits'] for f in frames)
    reward = min(1.0, full_hits*5 / (120*denominator/60))
    steady_reward=min(1.0,shot_hits*5/(120*max(HORIZON-WARMUP,len(assessed))/60))
    stale = [f for f in assessed if observed_boss_x is not None and
             f['player_dx']*(observed_boss_x-f['player_x'])>0 and
             f['player_dx']*(f['boss_x']-f['player_x'])<0]
    moving = [f for f in assessed if abs(f['player_dx'])>1e-9 and not f['respawn']]
    full_moving = [f for f in frames if abs(f['player_dx'])>1e-9 and not f['respawn']]
    full_stale = [f for f in full_moving if observed_boss_x is not None and
                  f['player_dx']*(observed_boss_x-f['player_x'])>0 and
                  f['player_dx']*(f['boss_x']-f['player_x'])<0]
    steady_away=sum(f['player_dx']*(f['boss_x']-f['player_x'])<0 for f in moving)
    steady_stale=len([f for f in stale if not f['respawn']])
    return dict(tracking_reward=reward, steady_tracking_reward=steady_reward,
        shot_damage=full_hits*5,shot_hits=full_hits,
        full_window_longest_eligible_no_hit_ticks=longest_run([eligible(f) and f['shot_hits']==0 for f in frames]),
        shot_damage_after_warmup=shot_hits*5,
        shot_hits_after_warmup=shot_hits, shot_damage_warmup=sum(f['shot_hits']*5 for f in frames[:warmup]),
        bomb_damage=sum(f['bomb_orb_hits']*30 for f in frames),
        actual_hp_loss=sum(f['hp_loss'] for f in frames),
        logical_ticks=len(frames),assessed_ticks=len(assessed),
        longest_eligible_no_hit_ticks=longest_run([eligible(f) and f['shot_hits']==0 for f in assessed]),
        eligible_no_hit_ticks=sum(eligible(f) and f['shot_hits']==0 for f in assessed),
        not_shooting_alive_ticks=sum(f['alive'] and not f['held'][1] for f in assessed),
        dead_ticks=sum(not f['alive'] for f in assessed),
        instantaneous_alignment_fraction=(sum(abs(f['player_x']-f['boss_x'])<20 for f in assessed)/len(assessed) if assessed else None),
        mean_abs_horizontal_error=(sum(abs(f['player_x']-f['boss_x']) for f in assessed)/len(assessed) if assessed else None),
        # Unprefixed fields retain their old steady-window semantics for compatibility.
        moving_ticks=len(moving),moving_away_from_current_boss_ticks=steady_away,
        stale_position_chase_ticks=steady_stale,
        steady_moving_ticks=len(moving),steady_moving_away_from_current_boss_ticks=steady_away,
        steady_stale_position_chase_ticks=steady_stale,
        full_window_moving_ticks=len(full_moving),
        full_window_moving_away_from_current_boss_ticks=sum(f['player_dx']*(f['boss_x']-f['player_x'])<0 for f in full_moving),
        full_window_stale_position_chase_ticks=len(full_stale),
        safety=dict(hits=sum(f['hits'] for f in frames),deaths=sum(f.get('deaths',f['hits']) for f in frames),
            lives_before=frames[0].get('lives_before') if frames else None,
            lives_after=frames[-1].get('lives_after') if frames else None,
            bombs_used=sum(f['bombs_used'] for f in frames),
            net_bombs_used=sum(f.get('net_bombs_used',f['bombs_used']) for f in frames),
            bombs_gained=sum(f.get('bombs_gained',0) for f in frames)))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(directory):
    summary=load(directory/'summary.json')
    return dict(summary=summary,actions=[a for a in rows(directory/'actions.jsonl') if a.get('status','applied')=='applied'],expected=load(directory/'final_state.json'))


def verify(env, original):
    # A mixed batch verifies the human source first; reset preserves control mode.
    # Disable human input before replaying API plans in this private evaluator.
    env.page.evaluate('research.setHuman(false)')
    final=replay(env,original)
    expected=original['expected'].get('state',original['expected'])
    expected={k:v for k,v in expected.items() if k!='clock'}
    result=compare_engine_state(final['state'],expected)
    if not result['bounded_float']:raise ValueError(f'Original full replay mismatch: {result}')
    return result


def episode(args):
    original=source(args.episode)
    with BrowserEnv(args.url) as env:
        verified=verify(env,original)
        env.reset(original['summary']['seed'])
        run=trace(env,actions=original['actions'],stop_visual=original['summary']['visual_frames'])
        expected=original['expected'].get('state',original['expected'])
        expected={k:v for k,v in expected.items() if k!='clock'}
        trace_verified=compare_engine_state(run['final']['state'],expected)
        if not trace_verified['bounded_float']:raise ValueError('Instrumented trace changed final original state')
        if run['final']['clock']['visual_frame']!=original['summary']['visual_frames']:raise ValueError('Trace endpoint differs')
    windows=[]
    # User's seconds refer to video/visual clock, including cutins.
    for start,end in args.window:
        selected=[f for f in run['frames'] if start*60<=f['visual_frame']<end*60]
        windows.append(dict(start_video_s=start,end_video_s=end,metrics=score_trace(selected,warmup=0),frames=selected))
    return dict(source_verification=verified,trace_final_verification=trace_verified,source=str(args.episode),
        source_actions_sha256=digest(args.episode/'actions.jsonl'),
        episode_metrics=score_trace(run['frames'],warmup=0),windows=windows)


def validated_comparisons(dataset, manifest, root):
    directory=root/'comparison' if (root/'comparison').is_dir() else root
    paths=sorted(directory.glob('call_*/comparison.json'))
    if not paths:raise ValueError('No completed comparison answers; refusing empty benchmark')
    entries={c['id']:c for c in manifest['cases']}
    if len(entries)!=len(manifest['cases']):raise ValueError('Duplicate dataset case IDs')
    coverage={key:set() for key in entries};answers=[]
    for path in paths:
        answer=load(path);case_id=answer['case_id']
        if case_id not in entries:raise ValueError('Comparison references unknown case')
        key=(answer['candidate'],answer['repeat'])
        if key in coverage[case_id]:raise ValueError('Duplicate candidate/repeat answer for a case')
        coverage[case_id].add(key)
        if digest(path.parent/'prompt.txt')!=answer['prompt_sha256']:raise ValueError('Prompt provenance mismatch')
        parse_plan(answer['response']['answer'])
        answers.append(answer)
    expected=set.union(*coverage.values())
    if not expected or any(value!=expected for value in coverage.values()):raise ValueError('Incomplete case/candidate/repeat coverage')
    for case in entries.values():
        if digest(dataset/case['input_file'])!=case['input_sha256']:raise ValueError('Public input hash mismatch')
        for image in case['images']:
            if digest(dataset/image['file'])!=image['sha256']:raise ValueError('Public PNG hash mismatch')
    return answers,dict(cases=len(entries),candidates=sorted({key[0] for key in expected}),
        candidate_repeat_pairs=len(expected),answers=len(answers))


def recorded_api_delay(case, original):
    """Private source age only, matched by captured visual frame and cohort."""
    issued_matches=[r for r in original['issued'] if r['seq']==case['source_seq']]
    if len(issued_matches)!=1:raise ValueError('Missing or duplicate source capture record')
    issued=issued_matches[0];visual=case['source_visual_frame']
    if issued['visual_frame']!=visual:raise ValueError('Source capture visual frame mismatch')
    matching=[a for a in original['actions'] if a.get('observed_frame')==visual]
    if len(matching)!=1:raise ValueError('Missing or ambiguous recorded applied action for observation')
    action=matching[0]
    winners=[r for r in original['issued'] if r['seq']==action['seq']]
    if len(winners)!=1:raise ValueError('Recorded winner has no unique issued record')
    winner=winners[0]
    if (winner.get('cohort_id',winner['seq'])!=issued.get('cohort_id',issued['seq'])
            or winner['visual_frame']!=visual
            or winner.get('image_sha256')!=issued.get('image_sha256')):
        raise ValueError('Recorded winner differs from source observation cohort')
    if action.get('capture_clock',{}).get('visual_frame')!=visual:
        raise ValueError('Recorded action capture clock differs from observation')
    frames=action['visual_frame']-visual
    if not isinstance(frames,int) or isinstance(frames,bool) or frames<0:
        raise ValueError('Invalid recorded visual action age')
    browser_s=(action['apply_clock']['wall_ms']-issued['capture_clock']['wall_ms'])/1000
    if not math.isfinite(browser_s) or browser_s<0:raise ValueError('Invalid recorded browser action age')
    record_sha=hashlib.sha256(json.dumps(action,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return dict(delay_s=frames/60,delay_visual_frames=frames,delay_kind='recorded_api_visual_age',
        recorded_browser_age_s=browser_s,recorded_visual_age_s=frames/60,
        recorded_capture_to_apply_monotonic_s=action.get('capture_to_apply_s'),
        source_applied_action_seq=action['seq'],source_cohort_id=issued.get('cohort_id',issued['seq']),
        source_applied_action_record_sha256=record_sha,
        source_action_hash_encoding='UTF-8 JSON sorted keys compact separators',
        source_actions_sha256=original['actions_sha256'],source_issued_sha256=original['issued_sha256'])


def delay_conditions(args, case, original=None):
    if not args.recorded_api_delays:
        return [dict(delay_s=d,delay_visual_frames=math.ceil(d*60),delay_kind='fixed_assumed_visual_age') for d in args.delays]
    if 'source_episode' in case:return [recorded_api_delay(case,original)]
    value=args.human_recorded_fallback_s
    if value is None:raise ValueError('Human cases have no recorded API age; provide explicit assumed fallback or select API cases only')
    if not math.isfinite(value) or value<0:raise ValueError('Invalid assumed human fallback age')
    return [dict(delay_s=value,delay_visual_frames=math.ceil(value*60),delay_kind='assumed_human_fallback_not_recorded')]


def cases(args):
    manifest=load(args.dataset/'manifest.json')
    comparisons,coverage=validated_comparisons(args.dataset,manifest,args.comparison)
    if args.expected_answers is not None and coverage['answers']!=args.expected_answers:raise ValueError('Answer count differs from frozen planned batch')
    diagnostic_kind='private_tracking_recorded_delay_diagnostic_v1' if args.recorded_api_delays else 'private_tracking_benchmark_v1'
    report=dict(dataset_manifest_sha256=digest(args.dataset/'manifest.json'),comparison_coverage=coverage,source_verification={},rollouts=[])
    if args.recorded_api_delays:report.update(post_selection_reuse=True,not_independent_validation=True,private_delay_labels=True)
    entries={case['id']:case for case in manifest['cases']}
    human=any('source_episode' not in c for c in entries.values())
    if human and args.human_source is None:raise ValueError('Human cases require --human-source')
    if human and args.recorded_api_delays and args.human_recorded_fallback_s is None:raise ValueError('Human cases require explicit assumed --human-recorded-fallback-s in recorded API diagnostic mode')
    sources={}
    with BrowserEnv(args.url) as env:
        env.page.evaluate("()=>{for(const key of ['drawImage','fillRect','clearRect','stroke','fill','fillText','strokeText'])CanvasRenderingContext2D.prototype[key]=()=>{};}")
        if human:
            sm=load(args.human_source/'manifest.json')
            if sm.get('provider')!='human' or sm.get('is_smoke'):raise ValueError('Not a real human demonstration')
            human_actions=rows(args.human_source/'actions.jsonl')
            expected=load(args.human_source/'final_state.json')
            final=replay_human(env,sm['seed'],human_actions,expected['clock']['visual_frame'])
            checked=compare_engine_state(final['state'],expected['state'])
            if not checked['bounded_float']:raise ValueError('Human full replay mismatch')
            report['source_verification'][str(args.human_source)]=checked
        for case in entries.values():
            if 'source_episode' in case:
                remote=case['source_episode']
                path=Path(remote)
                if args.source_root is not None and remote.startswith('/home/ubuntu/wzh/touhou-sol-study/'):
                    path=args.source_root/Path(remote).relative_to('/home/ubuntu/wzh/touhou-sol-study')
                if remote not in sources:
                    original=source(path);original['issued']=rows(path/'issued.jsonl')
                    original['actions_sha256']=digest(path/'actions.jsonl');original['issued_sha256']=digest(path/'issued.jsonl')
                    if case.get('issued_sha256') not in (None,original['issued_sha256']):raise ValueError('Source issued log provenance mismatch')
                    sources[remote]=original
                    report['source_verification'][remote]=verify(env,original)
        for answer in comparisons:
            case=entries[answer['case_id']]
            if digest(args.dataset/case['input_file'])!=case['input_sha256']:raise ValueError('Public input hash mismatch')
            if answer['response']['meta']['image_sha256s'] != [i['sha256'] for i in case['images']]:raise ValueError('Image provenance mismatch')
            original=sources.get(case.get('source_episode'))
            for condition in delay_conditions(args,case,original):
                delay=condition['delay_s']
                if 'source_episode' not in case:
                    if case.get('source_run')!=args.human_source.name:raise ValueError('Human source provenance mismatch')
                    observed=replay_human(env,sm['seed'],human_actions,case['source_visual_frame'])
                    public=load(args.dataset/case['input_file'])
                    if digest(args.dataset/case['input_file'])!=case['input_sha256']:raise ValueError('Human public input hash mismatch')
                    env.page.evaluate('research.setHuman(false)')
                    env.apply([public['observation']['held']+[1]])
                else:
                    original=sources[case['source_episode']]
                    issued=next(r for r in original['issued'] if r['seq']==case['source_seq'])
                    observed=replay(env,original,case['source_visual_frame'],issued.get('capture_clock',{}).get('wall_ms'))
                if observed['state']['tick']!=case['source_logical_frame']:raise ValueError('Observed logical frame mismatch')
                before=advance(env,case['source_visual_frame']+condition['delay_visual_frames'])
                plan=parse_plan(answer['response']['answer'])
                env.apply([a.keys+[a.duration] for a in plan])
                run=trace(env,ticks=HORIZON)
                report['rollouts'].append(dict(case_id=case['id'],candidate=answer['candidate'],repeat=answer['repeat'],
                    **condition,action_visual_frame=before['clock']['visual_frame'],
                    pre_action_hits=before['state']['hits']-observed['state']['hits'],
                    observed_boss_x_private=observed['state']['boss']['x'],
                    eligible_for_action=before['state']['status']=='playing',
                    source_status_after=run['final']['state']['status'],
                    prompt_sha256=answer.get('prompt_sha256'),
                    image_sha256s=answer['response']['meta']['image_sha256s'],
                    metrics=score_trace(run['frames'],observed_boss_x=observed['state']['boss']['x']),frames=run['frames']))
                save(args.output,dict(kind=diagnostic_kind,private_only=True,complete=False,**report))
    return report


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8796/game/')
    parser.add_argument('--output',type=Path,required=True)
    sub=parser.add_subparsers(dest='mode',required=True)
    ep=sub.add_parser('episode');ep.add_argument('episode',type=Path)
    ep.add_argument('--window',nargs=2,type=float,action='append',default=[])
    cs=sub.add_parser('cases');cs.add_argument('--dataset',type=Path,required=True)
    cs.add_argument('--comparison',type=Path,required=True)
    cs.add_argument('--source-root',type=Path);cs.add_argument('--human-source',type=Path)
    cs.add_argument('--delays',nargs='+',type=float,default=DELAYS)
    cs.add_argument('--expected-answers',type=int,help='Fail closed against the frozen planned answer count')
    cs.add_argument('--recorded-api-delays',action='store_true',help='Separate post-selection diagnostic using exact source observation-to-apply visual ages')
    cs.add_argument('--human-recorded-fallback-s',type=float,help='Explicit assumed human fallback; never labeled a recorded API age')
    args=parser.parse_args()
    if getattr(args,'window',None)==[]:args.window=[[17,20],[20,28],[17,28]]
    engine=Path(__file__).resolve().parents[1]/'dist/engine.mjs'
    if digest(engine)!=ENGINE_SHA256:raise ValueError('Frozen engine scoring constants no longer match source')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result=episode(args) if args.mode=='episode' else cases(args)
    output_kind='private_tracking_recorded_delay_diagnostic_v1' if args.mode=='cases' and args.recorded_api_delays else 'private_tracking_benchmark_v1'
    save(args.output,dict(kind=output_kind,private_only=True,complete=True,
        engine_sha256=ENGINE_SHA256,horizon_logical_ticks=HORIZON,warmup_logical_ticks=WARMUP,
        boundary='Private original-engine replay only; no state, future trajectory, human future inputs or score sent to an actor.',**result))
    print(json.dumps(dict(output=str(args.output),complete=True)))

if __name__=='__main__':main()
