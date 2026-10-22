"""Freeze public-only tracking fixtures from original API and human screenshots."""
import argparse
import copy
import json
import math
from pathlib import Path
import shutil
from .visual_devset import build, digest, load, save


def extract_past_memory(prompt, latest_frame):
    prefix='Your own past visual estimates (not engine truth), with each observed frame and boss coordinate: '
    for line in prompt.splitlines():
        if line.startswith(prefix):
            memory,_=json.JSONDecoder().raw_decode(line[len(prefix):])
            if not isinstance(memory,list):raise ValueError('Invalid past estimate list')
            output=[]
            for entry in memory:
                if set(entry)!={'frame','boss'} or type(entry['frame']) is not int or entry['frame']>latest_frame:
                    raise ValueError('Future or unsupported visual memory')
                boss=entry['boss']
                if not isinstance(boss,list) or len(boss)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in boss):
                    raise ValueError('Invalid boss visual estimate')
                output.append(copy.deepcopy(entry))
            return output
    return []


def freeze(api_root, human_dataset, output, profile, spec):
    """Private labels copied only to private/, never input.json or prompt."""
    episode=spec['episode']
    source=[{'id':f'api-tracking-{seq:03d}','episode':episode,'seq':seq,
             'tags':['tracking','delayed_intercept','turn_coverage'],
             'rubric':['Reward sustained shot contact through movement and subsequent idle firing; do not score current x-distance as correctness.',
                       'A return pass and a continued drift must be distinguished from visual evidence. Delayed safety remains a constraint.']}
            for seq in spec['real_sequences']]
    manifest=build(api_root,source,output,profile)
    for case in manifest['cases']:
        public=load(output/case['input_file'])
        prompt=(api_root/episode/f'decision_{case["source_seq"]:05d}'/'prompt.txt').read_text()
        memory=extract_past_memory(prompt,case['source_logical_frame'])
        if memory:public['observation']['visual_memory']=memory
        # Known historical profile provenance stays truthful in actor text.
        if 'control_age_kind' in profile:public['profile']['control_age_kind']=profile['control_age_kind']
        save(output/case['input_file'],public)
        case['input_sha256']=digest((output/case['input_file']).read_bytes())
    humans=load(human_dataset/'manifest.json')
    for ident in spec['human_case_ids']:
        original=next(c for c in humans['cases'] if c['id']==ident)
        case=copy.deepcopy(original)
        public=load(human_dataset/case['input_file'])
        public['profile']={k:profile[k] for k in ('p50_s','p95_s','control_age_p50_s','control_age_p95_s','control_age_kind') if k in profile}
        dest=output/'cases'/ident;dest.mkdir()
        for image in case['images']:
            data=(human_dataset/image['file']).read_bytes()
            if digest(data)!=image['sha256']:raise ValueError('Human PNG hash mismatch')
            (output/image['file']).write_bytes(data)
        save(output/case['input_file'],public)
        case['input_sha256']=digest((output/case['input_file']).read_bytes())
        shutil.copyfile(human_dataset/case['private_labels'],output/case['private_labels'])
        manifest['cases'].append(case)
    manifest.update(kind='tracking_intercept_visual_development',source_selection=spec['source_selection'],
                    memory_boundary='Only estimates in each original already-issued prompt; same public memory for every candidate. No future boss coordinates or human controls.',
                    score_boundary='Inputs are public. Counterfactual engine truth and future shot contacts belong exclusively to private scoring.')
    save(output/'manifest.json',manifest)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('api-root','human-dataset','output','profile'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--spec',type=Path,default=Path(__file__).with_name('tracking_cases_v1.json'))
    a=p.parse_args();m=freeze(a.api_root,a.human_dataset,a.output,load(a.profile),load(a.spec))
    print(json.dumps({'cases':len(m['cases']),'output':str(a.output)}))
