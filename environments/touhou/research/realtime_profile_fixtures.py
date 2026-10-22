"""Freeze serial API fixtures from completed subscription simulation cohorts.

Only known simulator-only appendices are deleted. Game policy, observations,
visual memory, race gating, action schema, and historical latency context remain
byte-for-byte. No API/model calls are made.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import struct

from .control_delays import read_rows
from .wire_schema import grounded_schema, schema_hash

JOINT='\nDelay condition: entire candidate readiness vectors are jointly resampled from earlier completed real API episodes, retaining observed launch skew, correlation, and control-pipeline overhead. These are past measurements, not the delay of this request.\n'
TERMINAL='\nEarly-action capacity simulation: a complete legal answer can take effect before its request releases its concurrency slot. Readiness and terminal slot delays are jointly resampled from historical timing; any censored terminal tail follows the declared profile model. Sampled per-request delays are hidden.\n'
STRESS='\nArtificial latency stress: simulated control delays are {scale:g} times the historical measurements above. This is a declared development assumption, not a new API measurement or the known delay of this request. Account for this factor when predicting threats and alignment.\n'


def digest(data):return hashlib.sha256(data).hexdigest()


def remove_sim_appendices(source,config):
    source.decode('utf-8')
    if config.get('mode')!='sim' or config.get('cohort_delay')!='empirical_joint' or config.get('decision_fanout',1)<=1:
        raise ValueError('Requires empirical joint fanout simulation source')
    scale=config.get('latency_scale',1)
    if type(scale) not in (int,float) or not math.isfinite(scale) or scale<=0: raise ValueError('Invalid latency scale')
    expected=[('joint_delay',JOINT)]
    if config.get('simulation_terminal_hold',False):expected.append(('early_terminal_capacity',TERMINAL))
    if scale!=1:expected.append(('artificial_stress',STRESS.format(scale=scale)))
    spans=[]
    for label,text in expected:
        data=text.encode()
        if source.count(data)!=1: raise ValueError('Expected exactly one simulator appendix: '+label)
        start=source.index(data);spans.append((start,start+len(data),label,data))
    spans.sort();parts=[];cursor=0;audit=[]
    for start,end,label,data in spans:
        if start<cursor: raise ValueError('Overlapping simulator appendices')
        parts.append(source[cursor:start]);cursor=end
        audit.append({'label':label,'source_start_byte':start,'source_end_byte':end,'removed_bytes':len(data),'removed_utf8':data.decode()})
    parts.append(source[cursor:]);result=b''.join(parts)
    for marker in (b'Delay condition: entire candidate readiness vectors',b'Early-action capacity simulation:',b'Artificial latency stress:'):
        if marker in result: raise ValueError('Unrecognized or repeated simulator appendix remains')
    if len(source)-len(result)!=sum(item['removed_bytes'] for item in audit): raise ValueError('Deletion accounting mismatch')
    return result,audit


def parse_quotas(text):
    try:
        pairs=[part.split(':') for part in text.split(',')]
        if any(len(pair)!=2 for pair in pairs): raise ValueError()
        quotas={int(n):int(count) for n,count in pairs}
        if len(quotas)!=len(pairs) or set(quotas)!={1,2,3} or any(count<1 for count in quotas.values()): raise ValueError()
        return quotas
    except (ValueError,TypeError):raise ValueError('Counts must specify positive quotas for all strata, e.g. 1:1,2:1,3:19')


def build_fixtures(episodes,output,quotas=None):
    quotas=quotas or {1:1,2:1,3:19}
    if set(quotas)!={1,2,3} or any(type(n) is not int or type(count) is not int or count<1 for n,count in quotas.items()):
        raise ValueError('Positive quotas for image strata 1/2/3 required')
    paths=sorted(Path(path).resolve() for path in episodes)
    if not paths or len(paths)!=len(set(paths)):raise ValueError('Unique source episodes required')
    pool=[];sources=[];identity=None;candidate=None
    for episode in paths:
        config=json.loads((episode/'config.json').read_text());summary=json.loads((episode/'summary.json').read_text())
        if summary.get('complete') is not True or config.get('provider')!='subscription' or config.get('mode')!='sim':
            raise ValueError('Requires completed subscription simulation episodes')
        if config.get('structured') is not True or config.get('max_duration',48)!=48 or config.get('max_output_tokens')!=512:
            raise ValueError('Requires structured source, duration 48 and frozen API output cap 512')
        chunks=config.get('chunk_size',1);schema=grounded_schema(chunks,48);schema_digest=schema_hash(schema)
        this_identity=('gpt-6.1-sol','low',chunks,schema_digest,512)
        if identity is not None and identity!=this_identity:raise ValueError('Mixed source action/model configurations')
        identity=this_identity
        if not isinstance(config.get('candidate'),str) or not config['candidate']:raise ValueError('Source candidate required')
        if candidate is not None and candidate!=config['candidate']:raise ValueError('Mixed source candidates')
        candidate=config['candidate']
        issued=read_rows(episode/'issued.jsonl');decisions=read_rows(episode/'decisions.jsonl')
        results={r['seq']:r for r in decisions};seqs=[r['seq'] for r in issued]
        if len(set(seqs))!=len(seqs) or len(results)!=len(decisions) or set(results)!=set(seqs):
            raise ValueError('Completed/issued sequences must match exactly')
        groups=defaultdict(list)
        for row in issued:groups[row['cohort_id']].append(row)
        source={'episode':str(episode),'candidate':candidate,'seed':config['seed']}
        sources.append(source)
        for cohort,rows in sorted(groups.items()):
            rows=sorted(rows,key=lambda r:r['fanout_index']);k=config['decision_fanout']
            if len(rows)!=k or [r['fanout_index'] for r in rows]!=list(range(k)) or any(r.get('decision_fanout')!=k for r in rows):
                raise ValueError('Incomplete or duplicate cohort slots')
            signatures=set()
            for row in rows:
                result=results[row['seq']];meta=result['meta']
                if meta.get('model')!='gpt-6.1-sol' or meta.get('effort')!='low' or meta.get('output_schema_sha256')!=schema_digest:
                    raise ValueError('Native request model/effort/schema mismatch')
                for key in ('cohort_id','fanout_index','visual_frame','image_frames','prompt_sha256','image_sha256'):
                    if row.get(key)!=result.get(key):raise ValueError('Issued/completed metadata mismatch')
                if meta.get('image_sha256s')!=row['image_sha256']:raise ValueError('Native image hash mismatch')
                signatures.add((row['prompt_sha256'],tuple(row['image_sha256']),tuple(row['image_frames'])))
            if len(signatures)!=1:raise ValueError('Same-cohort race inputs differ')
            selected=rows[0];directory=episode/f"decision_{selected['seq']:05d}"
            prompt=(directory/'prompt.txt').read_bytes()
            if digest(prompt)!=selected['prompt_sha256']:raise ValueError('Source prompt hash mismatch')
            images=[(directory/f'image_{i}.png').read_bytes() for i in range(len(selected['image_frames']))]
            if not 1<=len(images)<=3 or [digest(data) for data in images]!=selected['image_sha256']:
                raise ValueError('Source image count/hash mismatch')
            for image in images:
                if image[:8]!=b'\x89PNG\r\n\x1a\n' or len(image)<24:raise ValueError('Invalid source PNG')
                w,h=struct.unpack('>II',image[16:24])
                if not (0<w<=640 and 0<h<=480):raise ValueError('Source PNG exceeds API bounds')
            transformed,deletions=remove_sim_appendices(prompt,config)
            fingerprint=digest(transformed+b'\0'+json.dumps(selected['image_sha256'],separators=(',',':')).encode())
            pool.append({'episode':str(episode),'cohort_id':cohort,'seq':selected['seq'],'slot':0,'image_count':len(images),
                'image_frames':selected['image_frames'],'source_prompt_bytes':len(prompt),'prompt_bytes':len(transformed),
                'deletions':deletions,'fingerprint':fingerprint,'prompt':transformed,'images':images})
    counts={n:0 for n in quotas};selected=[];selection=[];seen=set()
    for entry in pool:
        n=entry['image_count'];fingerprint=entry['fingerprint']
        reason='selected'
        if fingerprint in seen:reason='duplicate_input_skipped'
        elif counts[n]>=quotas[n]:reason='quota_already_filled'
        else:selected.append(entry);counts[n]+=1
        seen.add(fingerprint)
        selection.append({key:entry[key] for key in ('episode','cohort_id','seq','slot','image_count')}|{'selection':reason})
    if counts!=quotas:raise ValueError('Insufficient distinct cohorts: requested '+str(quotas)+' but selected '+str(counts)+'; add completed seeds or explicitly lower counts')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    fixtures=[];audit=[]
    for index,entry in enumerate(selected):
        prefix=f"fixture_{index:03d}_{entry['image_count']}img";names=[]
        for i,data in enumerate(entry['images']):
            name=f'{prefix}_{i}.png';(output/name).write_bytes(data);names.append(name)
        fixtures.append({'name':prefix,'prompt':entry['prompt'].decode(),'images':names})
        audit.append({key:value for key,value in entry.items() if key not in ('prompt','images','fingerprint')}|{'fixture_name':prefix,'output_image_paths':names})
    model_config={'model':'gpt-6.1-sol','tier':'ultrafast','effort':'low','max_output_tokens':512,'detail':'high','max_chunks':identity[2],'max_duration':48}
    schema=grounded_schema(identity[2],48)
    (output/'schema.json').write_text(json.dumps(schema,indent=2)+'\n')
    manifest={'kind':'exact_realtime_task_minus_sim_appendices','version':1,'candidate':candidate,'counts':{str(n):c for n,c in counts.items()},'samples_per_fixture':1,'model_configuration':model_config,'fixtures':fixtures,
        'historical_latency_context_preserved':True,'limitations':['Game task, observations, visual memory, action schema and gating remain byte-identical after deleting only exact simulator appendices.',
            'Historical aggregate latency context remains in these fixtures. Future real evaluation using newly calibrated scalar latency context has a disclosed prompt difference.',
            'This serial fixture distribution measures recorded candidate inputs; it is not a new concurrent latency measurement or proof of full-episode policy performance.']}
    (output/'fixtures.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    (output/'audit.json').write_text(json.dumps({'sources':sources,'selection':selection,'fixtures':audit,'model_configuration':model_config},indent=2,ensure_ascii=False)+'\n')
    return {'output':str(output),'fixture_count':len(fixtures),'candidate':candidate,'counts':counts}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episodes',nargs='+',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--counts',default='1:1,2:1,3:19');args=parser.parse_args()
    print(json.dumps(build_fixtures(args.episodes,args.output,parse_quotas(args.counts))))

if __name__=='__main__':main()
