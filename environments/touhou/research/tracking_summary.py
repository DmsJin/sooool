"""Summarize a frozen private tracking batch; never calls a model or browser."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from statistics import mean

from .tracking_benchmark import DELAYS, ENGINE_SHA256, HORIZON, WARMUP

GATES = ('hits','deaths','bombs_used','not_shooting_alive_ticks')


def number(value, label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
        raise ValueError(f'Invalid nonnegative finite metric: {label}')
    return value


def validated_rows(report, baseline, expected_rows):
    if report.get('kind')!='private_tracking_benchmark_v1' or report.get('complete') is not True:
        raise ValueError('Input is not a completed tracking benchmark')
    if report.get('engine_sha256')!=ENGINE_SHA256 or report.get('horizon_logical_ticks')!=HORIZON or report.get('warmup_logical_ticks')!=WARMUP:
        raise ValueError('Frozen engine/horizon contract mismatch')
    checks=report.get('source_verification',{})
    if not checks or any(v.get('bounded_float') is not True for v in checks.values()):
        raise ValueError('Missing or failed source replay verification')
    rows=report.get('rollouts',[])
    if len(rows)!=expected_rows or not rows:raise ValueError('Incomplete frozen row count')
    grouped={};seen=set()
    for row in rows:
        candidate=row['candidate'];key=(row['case_id'],row['repeat'],row['delay_s'])
        if not isinstance(row['repeat'],int) or isinstance(row['repeat'],bool) or row['repeat']<0:
            raise ValueError('Invalid repeat index')
        if row['delay_s'] not in DELAYS:raise ValueError('Delay differs from frozen measured assumptions')
        identity=(candidate,)+key
        if identity in seen:raise ValueError('Duplicate candidate/case/repeat/delay pair')
        seen.add(identity);grouped.setdefault(candidate,{})[key]=row
        metrics=row['metrics']
        for field in ('shot_damage','shot_hits','shot_damage_after_warmup','full_window_longest_eligible_no_hit_ticks','not_shooting_alive_ticks','logical_ticks'):
            number(metrics[field],field)
        if metrics['shot_damage']!=metrics['shot_hits']*5:raise ValueError('Shot damage differs from frozen scoring')
        if metrics['logical_ticks']>HORIZON:raise ValueError('Counterfactual window exceeds frozen horizon')
        for field in ('hits','deaths','bombs_used'):number(metrics['safety'][field],field)
    if baseline not in grouped:raise ValueError('Missing baseline candidate')
    keys=set(grouped[baseline]);cases={key[0] for key in keys};repeats={key[1] for key in keys}
    expected={(case,repeat,delay) for case in cases for repeat in repeats for delay in DELAYS}
    if keys!=expected or any(set(value)!=expected for value in grouped.values()):
        raise ValueError('Incomplete matched case/repeat/delay coverage')
    coverage=report.get('comparison_coverage',{})
    if not isinstance(coverage.get('answers'),int):raise ValueError('Missing original answer coverage count')
    if (coverage.get('cases')!=len(cases) or coverage.get('candidates')!=sorted(grouped)
            or coverage.get('answers')*len(DELAYS)!=len(rows)
            or coverage.get('candidate_repeat_pairs')!=len(grouped)*len(repeats)):
        raise ValueError('Rows disagree with original frozen comparison coverage')
    return grouped,sorted(expected),dict(cases=len(cases),repeats=len(repeats),delays=DELAYS,
        candidates=sorted(grouped),rows=len(rows),paired_rows_per_candidate=len(expected))


def gate_totals(rows):
    return dict(hits=sum(r['metrics']['safety']['hits'] for r in rows),
        deaths=sum(r['metrics']['safety']['deaths'] for r in rows),
        bombs_used=sum(r['metrics']['safety']['bombs_used'] for r in rows),
        not_shooting_alive_ticks=sum(r['metrics']['not_shooting_alive_ticks'] for r in rows))


def describe(rows):
    metrics=[r['metrics'] for r in rows]
    return dict(rows=len(rows),shot_damage_mean=mean(m['shot_damage'] for m in metrics),
        steady_shot_damage_mean=mean(m['shot_damage_after_warmup'] for m in metrics),
        longest_miss_ticks_mean=mean(m['full_window_longest_eligible_no_hit_ticks'] for m in metrics),
        longest_miss_ticks_max=max(m['full_window_longest_eligible_no_hit_ticks'] for m in metrics),
        terminal_win_windows=sum(r.get('source_status_after')=='won' for r in rows),
        gates=gate_totals(rows))


def summarize(report, baseline, expected_rows=144):
    grouped,keys,coverage=validated_rows(report,baseline,expected_rows)
    base=grouped[baseline];base_gates=gate_totals(list(base.values()));candidates={}
    for name,matched in grouped.items():
        rows=[matched[key] for key in keys];stats=describe(rows)
        failures=[field for field in GATES if stats['gates'][field]>base_gates[field]]
        deltas=[matched[key]['metrics']['shot_damage']-base[key]['metrics']['shot_damage'] for key in keys]
        paired=[]
        for key,delta in zip(keys,deltas):
            paired.append(dict(case_id=key[0],repeat=key[1],delay_s=key[2],shot_damage_delta=delta,
                steady_shot_damage_delta=matched[key]['metrics']['shot_damage_after_warmup']-base[key]['metrics']['shot_damage_after_warmup'],
                longest_miss_ticks_delta=matched[key]['metrics']['full_window_longest_eligible_no_hit_ticks']-base[key]['metrics']['full_window_longest_eligible_no_hit_ticks'],
                gate_deltas={field:gate_totals([matched[key]])[field]-gate_totals([base[key]])[field] for field in GATES}))
        per_case={case:describe([matched[key] for key in keys if key[0]==case]) for case in sorted({key[0] for key in keys})}
        for case,description in per_case.items():
            description['paired_shot_damage_delta_mean']=mean(p['shot_damage_delta'] for p in paired if p['case_id']==case)
        candidates[name]=dict(**stats,safety_gate_pass=not failures,safety_gate_failures=failures,
            gate_deltas={field:stats['gates'][field]-base_gates[field] for field in GATES},
            paired_shot_damage_delta_mean=mean(deltas),paired_improved=sum(d>0 for d in deltas),
            paired_tied=sum(d==0 for d in deltas),paired_worse=sum(d<0 for d in deltas),
            worst_paired_shot_damage_delta=min(deltas),per_case=per_case,
            per_delay={str(delay):describe([matched[key] for key in keys if key[2]==delay]) for delay in DELAYS},paired=paired)
    def ranking(name):
        stats=candidates[name]
        return (stats['shot_damage_mean'],-stats['longest_miss_ticks_mean'],stats['steady_shot_damage_mean'])
    selected=baseline
    # Baseline keeps exact ties; no hidden candidate-name preference.
    for name in sorted(candidates):
        if candidates[name]['safety_gate_pass'] and ranking(name)>ranking(selected):selected=name
    return dict(kind='private_tracking_selection_v1',complete=True,baseline=baseline,coverage=coverage,
        selected_candidate=selected,selection='retain_baseline' if selected==baseline else 'promote_for_episode_testing',
        selection_rule='Aggregate gross bombs/hits/deaths/alive nonshooting no increase, then full-window mean shot damage, lower mean longest miss, higher steady damage; exact ties retain baseline.',
        not_weight_training=True,not_heldout_success_evidence=True,
        full_episode_win_gate='Not evaluated by matched-window cases; enforce separately in frozen whole-episode trials.',
        candidates=candidates)


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline',required=True);parser.add_argument('--expected-rows',type=int,default=144)
    args=parser.parse_args();data=args.input.read_bytes();report=json.loads(data)
    result=summarize(report,args.baseline,args.expected_rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temporary=args.output.with_suffix('.tmp');temporary.write_text(json.dumps(result,indent=2,allow_nan=False));temporary.replace(args.output)
    print(json.dumps(dict(selected=result['selected_candidate'],selection=result['selection'],output=str(args.output))))

if __name__=='__main__':main()
