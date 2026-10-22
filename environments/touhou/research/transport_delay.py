"""Model a new joint control-delay condition; never calls models or APIs.

Transport historical candidate network ranks to a new serial marginal while
retaining each candidate's measured non-network readiness residual. This is a
sensitivity model, not a measurement of new concurrent service performance.
"""
import argparse
import bisect
import hashlib
import json
import math
import os
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def request_image_count(shape):
    if 'image_count' in shape:
        count = shape['image_count']
    else:
        images = shape['images']
        if not isinstance(images, list):raise ValueError('Invalid request image list')
        count = len(images)
    if type(count) is not int or count < 1:raise ValueError('Invalid request image count')
    return count


def finite(value, label, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError('Invalid finite value: '+label)
    return float(value)


def quantile(values, probability):
    probability = finite(probability, 'probability')
    if not values or not 0 <= probability <= 1:
        raise ValueError('Quantile requires samples and probability in [0,1]')
    values = sorted(finite(value, 'sample', positive=True) for value in values)
    at = (len(values)-1)*probability
    lower = math.floor(at);upper = math.ceil(at)
    return values[lower] + (values[upper]-values[lower])*(at-lower)


def transport(network, old_marginal, new_marginal):
    network = finite(network, 'network', positive=True)
    old = sorted(finite(value, 'old marginal', positive=True) for value in old_marginal)
    if not old:
        raise ValueError('Empty historical marginal')
    left, right = bisect.bisect_left(old, network), bisect.bisect_right(old, network)
    if left == right:
        raise ValueError('Candidate network value is absent from historical marginal')
    probability = (left+right)/(2*len(old))
    return quantile(new_marginal, probability), probability


def build_profile(joint_path, serial_path, source_root=None, expected_serial=21, expected_joint=74):
    joint_path,serial_path = Path(joint_path),Path(serial_path)
    old=load(joint_path)
    serial=[json.loads(line) for line in serial_path.read_text().splitlines() if line.strip()]
    if len(serial)!=expected_serial:
        raise ValueError('Unexpected serial sample count')
    if len(old['joint_delay_vectors_s'])!=expected_joint or len(old['image_counts'])!=expected_joint:
        raise ValueError('Unexpected historical joint vector count')
    k=old['k']
    if type(k) is not int or k<1:
        raise ValueError('Invalid cohort capacity')
    cohorts=[]
    for provenance in old['provenance']:
        original=Path(provenance['episode'])
        directory=Path(source_root)/original.relative_to('/home/ubuntu/wzh/touhou-sol-study') if source_root else original
        for name,expected in provenance['source_sha256'].items():
            if sha(directory/name)!=expected:
                raise ValueError('Source hash mismatch: '+str(directory/name))
        rows=[json.loads(line) for line in (directory/'decisions.jsonl').read_text().splitlines() if line.strip()]
        groups={}
        for row in rows:groups.setdefault(row['cohort_id'],[]).append(row)
        count=0
        for cohort_id,group in sorted(groups.items()):
            if cohort_id in provenance['excluded_terminal_cohorts']:continue
            group=sorted(group,key=lambda row:row['fanout_index'])
            if len(group)!=k or [row['fanout_index'] for row in group]!=list(range(k)):
                raise ValueError('Incomplete historical cohort')
            image_count=len(group[0]['image_frames'])
            if any(len(row['image_frames'])!=image_count for row in group):
                raise ValueError('Mixed observation shapes within cohort')
            readiness=[finite(row['completed_wall_s'],'completed wall')-(finite(row['capture_clock']['wall_ms'],'capture wall')/1000+finite(provenance['clock_offset_s'],'clock offset')) for row in group]
            index=len(cohorts)
            if index>=expected_joint:
                raise ValueError('More source cohorts than frozen vectors')
            expected=old['joint_delay_vectors_s'][index]
            if len(expected)!=k or any(abs(a-finite(b,'joint delay',positive=True))>1e-9 for a,b in zip(readiness,expected)) or image_count!=old['image_counts'][index]:
                raise ValueError('Historical vector/source alignment mismatch')
            network=[finite(row['meta']['total_s'],'network latency',positive=True) for row in group]
            if any(ready-time<0 for ready,time in zip(readiness,network)):
                raise ValueError('Negative historical non-network residual')
            cohorts.append({'episode':str(original),'cohort_id':cohort_id,'images':image_count,'readiness':readiness,'network':network})
            count+=1
        if count!=provenance['complete_cohorts']:
            raise ValueError('Historical source complete-cohort count mismatch')
    if len(cohorts)!=expected_joint:
        raise ValueError('Fewer source cohorts than frozen vectors')
    old_marginal={n:sorted(t for group in cohorts if group['images']==n for t in group['network']) for n in sorted(set(old['image_counts']))}
    new_marginal={n:[] for n in old_marginal}
    identities=set()
    for row in serial:
        meta=row['meta'];shape=meta['shape']
        if meta['valid'] is not True:
            raise ValueError('Invalid serial response in calibration')
        count=request_image_count(shape)
        if count not in new_marginal:
            raise ValueError('Unexpected new serial image count')
        new_marginal[count].append(finite(meta['total_s'],'serial complete latency',positive=True))
        identities.add(tuple(shape.get(key) for key in ('model','tier','effort','max_output_tokens','detail','schema_sha256')))
    if len(identities)!=1 or any(not values for values in new_marginal.values()):
        raise ValueError('Mixed request configurations or missing serial image shape')
    audit=[];vectors=[]
    for group in cohorts:
        mapped=[];probabilities=[];residual=[]
        for ready,network in zip(group['readiness'],group['network']):
            target,probability=transport(network,old_marginal[group['images']],new_marginal[group['images']])
            remainder=ready-network
            mapped.append(remainder+target);probabilities.append(probability);residual.append(remainder)
        vectors.append(mapped)
        audit.append({'episode':group['episode'],'cohort_id':group['cohort_id'],'image_count':group['images'],
                      'old_readiness_s':group['readiness'],'old_network_s':group['network'],
                      'preserved_non_network_s':residual,'old_network_midrank_cdf':probabilities,
                      'modeled_readiness_s':mapped})
    apply=finite(old['apply_overhead_s'],'apply overhead')
    if apply<0:raise ValueError('Negative apply overhead')
    selected=[min(vector)+apply for vector in vectors]
    old_selected=[min(vector)+apply for vector in old['joint_delay_vectors_s']]
    marginal=new_marginal[max(new_marginal)]
    singleton=[n for n,values in new_marginal.items() if len(values)==1]
    return {'kind':'modeled_marginal_transport','control_age_kind':'modeled_marginal_transport','version':1,'k':k,
            'samples_s':sorted(marginal),'p50_s':quantile(marginal,.5),'p95_s':quantile(marginal,.95),'latency_metric':'total_s',
            'not_serial_fastest_api_profile':True,'not_observed_concurrent_profile':True,
            'joint_delay_vectors_s':vectors,'image_counts':old['image_counts'],'apply_overhead_s':apply,
            'control_age_p50_s':quantile(selected,.5),'control_age_p95_s':quantile(selected,.95),
            'delay_definition':'Historical readiness minus historical complete network time, plus inverse new serial marginal CDF at historical same-image-count concurrent network midrank. Selected age adds unchanged apply overhead.',
            'provenance':{'past_real_joint_profile':str(joint_path),'new_serial_profile':str(serial_path),'past_real_sources':old['provenance']},
            'serial_configuration':dict(zip(('model','tier','effort','max_output_tokens','detail','schema_sha256'),next(iter(identities)))),
            'assumptions':['Modeled sensitivity condition, not a measurement of new concurrent API performance.',
                           'Non-singleton image shapes retain network rank/copula through monotone marginal transport. Candidate readiness ranks or the winning slot can change after residuals are added.',
                           'Singleton new marginals use constant mapping: their network ranks collapse and their one sample is not a slow-tail bound.',
                           'Historical launch/preparation/settlement/polling residuals are preserved; new concurrency effects or execution-path changes are not calibrated.',
                           'Empirical inverse CDF is linearly interpolated without tail extrapolation; rare unseen tails remain unknown.',
                           'No actual sampled delay, private engine state, or future source decisions may be sent to the player model.'],
            'singleton_constant_image_counts':singleton,
            'marginal_sample_counts':{'past_real':{str(n):len(v) for n,v in old_marginal.items()},'new_serial':{str(n):len(v) for n,v in new_marginal.items()}},
            'selected_age_summary':{'old_joint_min_plus_apply_p50':quantile(old_selected,.5),'old_joint_min_plus_apply_p95':quantile(old_selected,.95),
                                    'modeled_p50':quantile(selected,.5),'modeled_p95':quantile(selected,.95),
                                    'old_times_1_15_p50':quantile([x*1.15 for x in old_selected],.5),'old_times_1_15_p95':quantile([x*1.15 for x in old_selected],.95)},
            'minimum_preserved_non_network_s':min(x for group in audit for x in group['preserved_non_network_s']),
            'transport_audit':audit}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--joint',type=Path,required=True)
    parser.add_argument('--serial',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-root',type=Path)
    parser.add_argument('--expected-serial-count',type=int,default=21)
    parser.add_argument('--expected-joint-count',type=int,default=74)
    args=parser.parse_args()
    profile=build_profile(args.joint,args.serial,args.source_root,args.expected_serial_count,args.expected_joint_count)
    # Never overwrite an already-frozen condition.
    with args.output.open('x') as output:
        json.dump(profile,output,indent=2,allow_nan=False);output.flush();os.fsync(output.fileno())
    fd=os.open(args.output.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps({'output':str(args.output),'kind':profile['kind'],'control_age_p50_s':profile['control_age_p50_s'],'control_age_p95_s':profile['control_age_p95_s']}))


if __name__=='__main__':main()
