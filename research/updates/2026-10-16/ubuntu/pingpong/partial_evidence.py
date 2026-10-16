"""Strict public evidence resolution for development-only partial replay."""
import hashlib
import json


def digest(raw):return hashlib.sha256(raw).hexdigest()


def snapshot_bytes(seq,step,state,image_sha256,prompt):
    return json.dumps({'seq':seq,'step':step,'state':state,'image_sha256':image_sha256,
                       'prompt_sha256':digest(prompt.encode())},separators=(',',':')).encode()


def prompt_state(text):
    return json.loads(text.split('\nSTATE ',1)[1].split('\nIMAGE_META ',1)[0])


def resolve(source,row,postfork):
    """Never manufacture missing q. Unsent canceled requests remain explicitly qualified."""
    seq=row['seq'];directory=source/f'decision_{seq:05d}'
    parent=source/'observations'/f'{seq:05d}.json';input_path=directory/'input.json'
    canceled=any(r['ev']=='act_dropped' and r.get('seq')==seq and r.get('why')=='screen_unused_tail_cancel' for r in postfork)
    used=any(r['ev'] in ('model_visible','effect') and r.get('seq')==seq for r in postfork)
    canceled_unsent=not input_path.exists() and canceled and not used and not (directory/'result.json').exists()
    if not input_path.exists() and not canceled_unsent:
        raise ValueError(f'Missing input is not a documented unused canceled request seq={seq}')
    snapshot=None;recorded=None;text=None
    if parent.exists():
        raw=parent.read_bytes()
        if digest(raw)!=row.get('parent_observation_sha256'):raise ValueError(f'Parent snapshot seal mismatch seq={seq}')
        snapshot=json.loads(raw)
        if (snapshot['seq']!=seq or snapshot['step']!=row['k'] or snapshot['image_sha256']!=row['image_sha256']
                or snapshot['prompt_sha256']!=row.get('prompt_sha256')):
            raise ValueError(f'Parent snapshot provenance mismatch seq={seq}')
        recorded=snapshot['state']
    if input_path.exists():
        text=json.loads(input_path.read_text())['params']['input'][0]['text']
        if snapshot and digest(text.encode())!=snapshot['prompt_sha256']:
            raise ValueError(f'Worker input prompt differs from parent seq={seq}')
        if row.get('prompt_sha256') and digest(text.encode())!=row['prompt_sha256']:
            raise ValueError(f'Worker input prompt differs from issued hash seq={seq}')
        worker_state=prompt_state(text)
        if recorded is not None and recorded!=worker_state:
            raise ValueError(f'Worker STATE differs from parent seq={seq}')
        if recorded is None:recorded=worker_state
    return {'state':recorded,'worker_input_recorded':input_path.exists(),'parent_recorded':snapshot is not None,
            'canceled_unsent':canceled_unsent,'q_unrecorded_canceled':canceled_unsent and recorded is None}
