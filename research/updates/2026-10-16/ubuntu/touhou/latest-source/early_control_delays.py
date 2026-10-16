"""Calibrate historical early-JSON races, with separately modeled terminal slots.

No screenshots, game state, prompts, or actions are supplied to an actor. Callback
return bounds publication from above; old logs have no exact durable timestamp.
Terminal release is observed coordinator removal, not network completion. A tail
cohort drained after gameplay is censored and requires an explicit policy.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

from .control_delays import nonnegative, percentile, read_rows


def calibrate_early(episodes, k=4, apply_overhead_s=.02, terminal_tail_policy='error'):
    if type(k) is not int or k < 1: raise ValueError('K must be positive integer')
    if terminal_tail_policy not in ('error', 'exclude', 'durable_plus_median_poll_lag'):
        raise ValueError('Unknown terminal tail policy')
    overhead=nonnegative(apply_overhead_s,'apply overhead')
    vectors=[]; terminals=[]; counts=[]; provenance=[]; ages=[]; capture_ages=[]; start_ages=[]; frame_ages=[]
    for episode in map(Path,episodes):
        summary=json.loads((episode/'summary.json').read_text()); config=json.loads((episode/'config.json').read_text())
        if not (summary.get('complete') is True and summary.get('terminal_accounting_complete') is True):
            raise ValueError('Requires fully verified terminal accounting')
        if not (config.get('mode')=='realtime' and config.get('provider')=='api' and config.get('early_action_delivery') is True and config.get('speed')==1 and config.get('decision_fanout')==k):
            raise ValueError('Requires original-speed early API race with matching K')
        issued=read_rows(episode/'issued.jsonl'); completed=read_rows(episode/'decisions.jsonl'); actions=read_rows(episode/'actions.jsonl')
        if not actions: raise ValueError('Missing applied actions')
        by_seq={r['seq']:r for r in issued}; results={r['seq']:r for r in completed}
        if len(by_seq)!=len(issued) or len(results)!=len(completed) or set(by_seq)!=set(results):
            raise ValueError('Issued/completed sequences must match exactly')
        offset=statistics.median(nonnegative(a['applied_wall_s'],'apply wall')-nonnegative(a['apply_clock']['wall_ms'],'apply clock')/1000 for a in actions)
        if not math.isfinite(offset): raise ValueError('Invalid clock offset')
        lags=[]
        for row in completed:
            if 'completed_wall_s' in row:
                lags.append(nonnegative(row['completed_wall_s']-row['meta']['stage_timing']['result_durable_wall_s'],'coordinator poll lag'))
        if not lags: raise ValueError('No observed coordinator release lag')
        poll_lag=statistics.median(lags)
        groups=defaultdict(list); hashes={name:hashlib.sha256((episode/name).read_bytes()).hexdigest() for name in ('config.json','summary.json','issued.jsonl','decisions.jsonl','actions.jsonl')}
        modeled=[]; excluded=[]; early_hashes={}
        for row in issued: groups[row['cohort_id']].append(row)
        for cohort,members in sorted(groups.items()):
            if len(members)!=k or sorted(m['fanout_index'] for m in members)!=list(range(k)):
                raise ValueError('Incomplete/duplicate cohort slots')
            vector=[]; terminal=[]; image_counts=set(); censored=False
            for member in sorted(members,key=lambda x:x['fanout_index']):
                row=results[member['seq']]
                for field in ('cohort_id','fanout_index','visual_frame','capture_clock','image_frames'):
                    if row.get(field)!=member.get(field): raise ValueError('Issued/completed metadata mismatch')
                if member.get('decision_fanout')!=k: raise ValueError('Issued K mismatch')
                path=episode/f"decision_{member['seq']:05d}"/'early_result.json'
                early=json.loads(path.read_text()); early_hashes[str(path.relative_to(episode))]=hashlib.sha256(path.read_bytes()).hexdigest()
                if early['meta'].get('early_legal') is not True or row['meta'].get('early_legal_delivered') is not True or row['meta'].get('valid') is not True:
                    raise ValueError('Missing valid early and terminal delivery')
                if early['answer']!=row['answer']: raise ValueError('Early/terminal action mismatch')
                # callback return follows durable write and publication. It is an
                # upper bound, not an independently logged fsync-completed time.
                ready=nonnegative(early['meta']['stage_timing']['early_legal_ready_wall_s'],'early callback start')+nonnegative(row['meta']['early_callback_s'],'callback duration')
                observed=nonnegative(member['capture_clock']['wall_ms'],'capture clock')/1000+offset
                vector.append(nonnegative(ready-observed,'readiness'))
                if 'completed_wall_s' in row:
                    released=nonnegative(row['completed_wall_s'],'coordinator release')
                else:
                    censored=True
                    released=nonnegative(row['meta']['stage_timing']['result_durable_wall_s'],'durable terminal')+poll_lag
                if released<ready: raise ValueError('Terminal release precedes early publication')
                terminal.append(nonnegative(released-observed,'terminal delay'))
                image_counts.add(len(member['image_frames']))
            if len(image_counts)!=1 or next(iter(image_counts))<1: raise ValueError('Invalid image stratum')
            if censored:
                if cohort!=max(groups): raise ValueError('Nonterminal censored cohort')
                if terminal_tail_policy=='error': raise ValueError('Terminal tail is censored; choose an explicit policy')
                if terminal_tail_policy=='exclude': excluded.append(cohort); continue
                modeled.append(cohort)
            vectors.append(vector); terminals.append(terminal); counts.append(image_counts.pop())
        for action in actions:
            source=by_seq[action['seq']]
            if action['observed_frame']!=source['visual_frame']: raise ValueError('Applied source mismatch')
            ages.append(nonnegative((action['apply_clock']['wall_ms']-source['capture_clock']['wall_ms'])/1000,'browser age'))
            capture_ages.append(nonnegative(action['capture_to_apply_s'],'capture completed age'))
            start_ages.append(nonnegative(action['capture_start_to_apply_s'],'capture started age'))
            frame_ages.append(nonnegative(action['age_frames']/60,'frame age'))
        provenance.append({'episode':str(episode),'clock_offset_s':offset,'issued_candidates':len(issued),'applied_count':len(actions),
            'cohorts':len(groups),'excluded_tail_cohorts':excluded,'modeled_terminal_tail_cohorts':modeled,
            'modeled_tail_poll_lag_s':poll_lag if modeled else None,'source_sha256':hashes,'early_file_sha256':early_hashes})
    if not vectors: raise ValueError('Empty profile')
    return {'kind':'posthoc_real_early_control_readiness','version':1,'k':k,'not_serial_fastest_api_profile':True,
        'delay_definition':'callback_start_wall_s + callback_elapsed_s - (capture_clock.wall_ms/1000 + median_clock_offset_s)',
        'publication_timestamp_kind':'measured_callback_return_upper_bound; exact fsync/publication timestamps were not logged',
        'terminal_definition':'coordinator completed_wall_s; censored tail follows explicit terminal_tail_policy',
        'terminal_tail_policy':terminal_tail_policy,'apply_overhead_s':overhead,'joint_delay_vectors_s':vectors,
        'joint_terminal_delay_vectors_s':terminals,'image_counts':counts,'provenance':provenance,
        'control_age_kind':'observed_early_browser_capture_to_apply','control_age_p50_s':percentile(ages,.5),'control_age_p95_s':percentile(ages,.95),
        'control_age_capture_completed_p50_s':percentile(capture_ages,.5),'control_age_capture_completed_p95_s':percentile(capture_ages,.95),
        'control_age_capture_started_p50_s':percentile(start_ages,.5),'control_age_capture_started_p95_s':percentile(start_ages,.95),
        'control_age_frames_as_s_p50':percentile(frame_ages,.5),'control_age_frames_as_s_p95':percentile(frame_ages,.95),'applied_count':len(ages)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episodes',nargs='+',type=Path);parser.add_argument('--k',type=int,default=4)
    parser.add_argument('--apply-overhead-s',type=float,default=.02)
    parser.add_argument('--terminal-tail-policy',choices=('error','exclude','durable_plus_median_poll_lag'),default='error')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    profile=calibrate_early(args.episodes,args.k,args.apply_overhead_s,args.terminal_tail_policy)
    with args.output.open('x') as target: target.write(json.dumps(profile,indent=2,allow_nan=False)+'\n')

if __name__=='__main__':main()
