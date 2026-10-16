"""Offline serial legal-action marginal transport for historical early races.

This is a declared latency model, never a measured new concurrent profile.
Source files are hashed and reconstructed before any marginal is transported.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path

from .control_delays import nonnegative, read_rows
from .early_control_delays import calibrate_early
from .transport_delay import quantile, sha, transport

IDENTITY=('model','tier','effort','max_output_tokens','detail','schema_sha256')


def identity(shape):
    if any(key not in shape for key in IDENTITY): raise ValueError('Incomplete request configuration')
    if any(not isinstance(shape[key],str) or not shape[key] for key in IDENTITY if key!='max_output_tokens'):
        raise ValueError('Invalid request configuration string')
    if type(shape['max_output_tokens']) is not int or shape['max_output_tokens']<1:
        raise ValueError('Invalid request output cap')
    if not isinstance(shape.get('images'),list) or not shape['images'] or any(not isinstance(v,str) or not v for v in shape['images']):
        raise ValueError('Invalid request image hashes')
    return tuple(shape[key] for key in IDENTITY)


def positive(value,label):
    value=nonnegative(value,label)
    if value==0: raise ValueError(label+' must be positive')
    return value


def compare_vectors(actual,expected,label):
    if not isinstance(expected,list) or len(actual)!=len(expected): raise ValueError(label+' population mismatch')
    for left,right in zip(actual,expected):
        if not isinstance(right,list) or len(left)!=len(right) or any(abs(a-nonnegative(b,label))>1e-8 for a,b in zip(left,right)):
            raise ValueError(label+' alignment mismatch')


def build_early_transport(joint_path,serial_path,source_episodes=None,expected_serial=None):
    joint_path,serial_path=Path(joint_path),Path(serial_path)
    old=json.loads(joint_path.read_text())
    if old.get('kind')!='posthoc_real_early_control_readiness': raise ValueError('Requires original observed early profile')
    k=old['k']
    if type(k) is not int or k<1: raise ValueError('Invalid K')
    if type(expected_serial) is not int or expected_serial<1: raise ValueError('Explicit positive expected_serial count required')
    serial=read_rows(serial_path)
    if len(serial)!=expected_serial: raise ValueError('Unexpected serial sample count')
    provenance=old['provenance']
    if not provenance: raise ValueError('Missing source provenance')
    override={}
    for path in source_episodes or []:
        path=Path(path).resolve()
        if path.name in override: raise ValueError('Ambiguous source episode basename')
        override[path.name]=path
    directories=[]
    for source in provenance:
        original=Path(source['episode']);directory=override.pop(original.name,original)
        directories.append(directory)
        if set(source['source_sha256'])!=set(('config.json','summary.json','issued.jsonl','decisions.jsonl','actions.jsonl')):
            raise ValueError('Incomplete source hash inventory')
        early=source.get('early_file_sha256',{})
        if not early: raise ValueError('Missing early action source hashes')
        for name,expected in {**source['source_sha256'],**early}.items():
            path=directory/name
            if path.resolve().is_relative_to(directory.resolve()) is not True:
                raise ValueError('Source path escapes episode')
            if sha(path)!=expected: raise ValueError('Source hash mismatch: '+str(path))
    if override: raise ValueError('Unused source episode override')
    rebuilt=calibrate_early(directories,k,old['apply_overhead_s'],old['terminal_tail_policy'])
    for actual,expected in zip(rebuilt['provenance'],provenance):
        if actual['early_file_sha256']!=expected['early_file_sha256']:
            raise ValueError('Incomplete or inconsistent early hash inventory')
        if abs(actual['clock_offset_s']-expected['clock_offset_s'])>1e-8:
            raise ValueError('Source clock-offset alignment mismatch')
    compare_vectors(rebuilt['joint_delay_vectors_s'],old['joint_delay_vectors_s'],'Readiness')
    compare_vectors(rebuilt['joint_terminal_delay_vectors_s'],old['joint_terminal_delay_vectors_s'],'Terminal')
    if rebuilt['image_counts']!=old['image_counts']: raise ValueError('Image stratum alignment mismatch')
    cohorts=[];identities=set();index=0
    for source,directory in zip(provenance,directories):
        groups=defaultdict(list)
        for row in read_rows(directory/'decisions.jsonl'): groups[row['cohort_id']].append(row)
        included=set(source.get('excluded_tail_cohorts',[]))
        for cohort,rows in sorted(groups.items()):
            if cohort in included:continue
            rows=sorted(rows,key=lambda x:x['fanout_index'])
            if len(rows)!=k or [r['fanout_index'] for r in rows]!=list(range(k)):
                raise ValueError('Invalid candidate cohort')
            vectors=[]
            for slot,row in enumerate(rows):
                meta=row['meta'];shape=meta['shape'];identities.add(identity(shape))
                if meta.get('valid') is not True: raise ValueError('Invalid historical response')
                images=len(row['image_frames'])
                if len(shape['images'])!=images or images!=old['image_counts'][index]: raise ValueError('Historical image shape mismatch')
                early=json.loads((directory/f"decision_{row['seq']:05d}"/'early_result.json').read_text())
                legal=positive(early['meta']['legal_action_s'],'historical legal duration')
                observed=nonnegative(row['capture_clock']['wall_ms'],'capture clock')/1000+source['clock_offset_s']
                launch=nonnegative(meta['stage_timing']['network_started_wall_s']-observed,'capture-to-network residual')
                ready=old['joint_delay_vectors_s'][index][slot]
                callback=nonnegative(ready-launch-legal,'callback/publication residual')
                tail=nonnegative(old['joint_terminal_delay_vectors_s'][index][slot]-ready,'terminal-ready tail')
                vectors.append({'seq':row['seq'],'legal_s':legal,'capture_to_network_s':launch,'publication_residual_s':callback,'terminal_ready_tail_s':tail})
            cohorts.append({'episode':source['episode'],'cohort_id':cohort,'image_count':old['image_counts'][index],'slots':vectors})
            index+=1
    if index!=len(old['joint_delay_vectors_s']) or len(identities)!=1:
        raise ValueError('Mixed historical request configurations or cohort alignment mismatch')
    historical_identity=next(iter(identities))
    old_marginal=defaultdict(list);new_marginal=defaultdict(list)
    for cohort in cohorts:
        old_marginal[cohort['image_count']].extend(slot['legal_s'] for slot in cohort['slots'])
    for row in serial:
        meta=row['meta'];shape=meta['shape']
        if meta.get('valid') is not True: raise ValueError('Invalid serial response')
        if identity(shape)!=historical_identity: raise ValueError('Serial/historical model, tier, effort, cap, detail or schema mismatch')
        count=len(shape['images'])
        if count not in old_marginal: raise ValueError('Unexpected serial image-count stratum')
        new_marginal[count].append(positive(meta['legal_action_s'],'serial legal duration'))
    if set(new_marginal)!=set(old_marginal): raise ValueError('Missing serial image-count stratum; no fallback')
    ready_vectors=[];terminal_vectors=[];audit=[]
    for cohort in cohorts:
        ready=[];terminal=[];slots=[]
        for slot in cohort['slots']:
            target,probability=transport(slot['legal_s'],old_marginal[cohort['image_count']],new_marginal[cohort['image_count']])
            r=slot['capture_to_network_s']+target+slot['publication_residual_s']
            ready.append(r);terminal.append(r+slot['terminal_ready_tail_s'])
            slots.append({**slot,'legal_midrank_cdf':probability,'modeled_legal_s':target,'modeled_readiness_s':r,'modeled_terminal_s':terminal[-1]})
        ready_vectors.append(ready);terminal_vectors.append(terminal)
        audit.append({**{key:cohort[key] for key in ('episode','cohort_id','image_count')},'slots':slots})
    overhead=nonnegative(old['apply_overhead_s'],'apply overhead')
    selected=[min(row)+overhead for row in ready_vectors]
    largest=max(new_marginal);samples=sorted(new_marginal[largest])
    return {'kind':'modeled_early_prompt_transport','control_age_kind':'modeled_early_prompt_transport','version':1,'k':k,
        'not_serial_fastest_api_profile':True,'not_observed_concurrent_profile':True,'latency_metric':'legal_action_s',
        'joint_delay_vectors_s':ready_vectors,'joint_terminal_delay_vectors_s':terminal_vectors,'image_counts':old['image_counts'],'apply_overhead_s':overhead,
        'control_age_p50_s':quantile(selected,.5),'control_age_p95_s':quantile(selected,.95),'samples_s':samples,'p50_s':quantile(samples,.5),'p95_s':quantile(samples,.95),
        'serial_configuration':dict(zip(IDENTITY,historical_identity)),
        'singleton_constant_image_counts':sorted(n for n,v in new_marginal.items() if len(v)==1),
        'marginal_sample_counts':{'past_real':{str(n):len(v) for n,v in old_marginal.items()},'new_serial':{str(n):len(v) for n,v in new_marginal.items()}},
        'provenance':{'past_real_joint_profile':str(joint_path),'past_real_joint_sha256':sha(joint_path),'new_serial_profile':str(serial_path),'new_serial_sha256':sha(serial_path),'past_real_sources':provenance},
        'delay_definition':'Map same-image historical early legal-action midranks to new serial legal-action durations; preserve capture-to-network and callback-publication residuals plus paired terminal-ready tails.',
        'assumptions':['Declared prompt-dependent transport model, not measured new concurrent API timing.',
            'Historical early legal durations include callback validation setup; serial legal_action_s measures completed JSON detection. Their small detection/validation difference is not recalibrated.',
            'Historical source hashes and reconstructed readiness/terminal vectors must match before transport.',
            'Historical within-stratum legal ranks/copula are retained monotonically; residual addition can change winners.',
            'Singleton new strata collapse to a constant legal duration and do not estimate slow tails.',
            'Historical network launch/preparation, publication, coordinator terminal tails and explicitly modeled censored tails are retained.',
            'Linear empirical quantiles do not extrapolate unseen rare tails. New service concurrency effects are unknown.',
            'No sampled request latency, private state, future trajectories or source screenshots may be sent to the actor.'],
        'actor_context':'Delay statistics below are a declared model for this candidate prompt: its serial API legal-action durations were mapped onto historical concurrent early-action ranks, retaining historical launch/publication residuals and paired terminal tails. These are modeled aggregate ages, not newly measured concurrent performance and not the sampled delay of this request. Single-sample image strata cannot characterize slow tails.',
        'transport_audit':audit}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--joint',type=Path,required=True);parser.add_argument('--serial',type=Path,required=True)
    parser.add_argument('--source-episode',type=Path,action='append');parser.add_argument('--expected-serial-count',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    profile=build_early_transport(args.joint,args.serial,args.source_episode,args.expected_serial_count)
    with args.output.open('x') as target:
        json.dump(profile,target,indent=2,allow_nan=False);target.flush();os.fsync(target.fileno())
    fd=os.open(args.output.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps({key:profile[key] for key in ('kind','control_age_p50_s','control_age_p95_s','singleton_constant_image_counts')}))

if __name__=='__main__':main()
