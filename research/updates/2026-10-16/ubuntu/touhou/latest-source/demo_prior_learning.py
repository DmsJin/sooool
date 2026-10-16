"""Six serial subscription turns learn provisional visual priors from a completed demo.

This is offline training, never a realtime player input adapter. Original PNGs
and already-completed demonstration controls only; no state/engine/future formula.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def load(path):return json.loads(Path(path).read_text())
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def rows(path):return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
def sha(data):return hashlib.sha256(data).hexdigest()


def learning_schema():
    def obj(properties):return {'type':'object','additionalProperties':False,'required':list(properties),'properties':properties}
    text={'type':'string'}
    estimate=obj({'frame':{'type':'integer'},'x':{'type':'number'},'y':{'type':'number'}})
    hypothesis=obj({'principle':text,'visual_or_demonstration_evidence':text,'limitation_or_test':text})
    return obj({'boss_estimates':{'type':'array','minItems':1,'maxItems':3,'items':estimate},
                'motion_notes':{'type':'array','minItems':1,'maxItems':4,'items':text},
                'policy_hypotheses':{'type':'array','minItems':2,'maxItems':4,'items':hypothesis},
                'chunking_hypothesis':obj({'recommend_move_hold_chunks':{'type':'boolean'},'reason':text,'risk_or_test':text}),
                'limitations':{'type':'array','minItems':1,'maxItems':4,'items':text}})


def prepare(source:Path,output:Path):
    verification=load(source/'verification.json')
    manifest=load(source/'manifest.json')
    if not verification.get('verified') or not verification.get('bounded_float') or manifest.get('provider')!='human':raise ValueError('Verified human demo required')
    all_frames=rows(source/'frames.jsonl');actions=rows(source/'actions.jsonl')
    selected=[]
    for target in range(120,1921,120):
        eligible=[r for r in all_frames if r['frame']<=target and r['clock'].get('intro',0)==0 and r['frame']>0]
        if not eligible:raise ValueError('Missing past non-intro frame')
        row=max(eligible,key=lambda r:(r['frame'],r['clock']['visual_frame']))
        image=source/row['png'];data=image.read_bytes()
        if sha(data)!=row['sha256']:raise ValueError('Original screenshot hash mismatch')
        selected.append({'target_frame':target,'frame':row['frame'],'visual_frame':row['clock']['visual_frame'],
                         'held':row['held'],'source_png':row['png'],'sha256':row['sha256'],'data':data})
    output.mkdir(parents=True,exist_ok=False);(output/'images').mkdir()
    for index,row in enumerate(selected):
        path=f'images/image_{index:02d}.png';(output/path).write_bytes(row.pop('data'));row['png']=path
    # 16 chronological frames => four3-image and two2-image batches.
    batches=[];offset=0;last_visual=-1
    for count in (3,3,3,3,2,2):
        images=selected[offset:offset+count];offset+=count;last=images[-1]['visual_frame']
        controls=[{'logical_frame':a['logical_frame'],'visual_frame':a['visual_frame'],'action':a['action']}
                  for a in actions if last_visual<a['visual_frame']<=last]
        batches.append({'index':len(batches),'images':images,'past_completed_demonstration_controls':controls})
        last_visual=last
    bundle={'kind':'offline_completed_human_demonstration_learning','source_run':source.name,
            'source_manifest_sha256':sha((source/'manifest.json').read_bytes()),
            'source_verification_sha256':sha((source/'verification.json').read_bytes()),
            'source_actions_sha256':sha((source/'actions.jsonl').read_bytes()),
            'human_summary':{'focus_fraction':.993,'moving_logical_time_fraction':.227,'median_moving_segment_frames':5,
                             'won_game_seconds':33.9,'hits':0,'bombs_used':0},
            'input_boundary':'Offline completed demo only. No engine/source/state, no future controls beyond current batch last screenshot, no evaluation case future labels.',
            'batches':batches}
    save(output/'bundle.json',bundle);return bundle


INSTRUCTION='''Study this completed human demonstration of the same easy Touhou Kaguya boss game. This is OFFLINE training, not a live action decision. You are gpt-6.1-sol studying original screenshots and recorded PAST human controls. The small boss is near the top; the red/white Reimu player fires upward red talismans. Large translucent portrait and friendly bomb orbits are not dangerous enemy bullets. The screenshots are chronological, in full640x480 pixel coordinates. Controls: 0stay,1up,2up-right,3right,4down-right,5down,6down-left,7left,8up-left; remaining fields are shoot,focus,bomb. You may use only these visible frames, already-completed human controls and your own previous visual estimates/notes. Do not use tools, files, code, engine truth or external sources.
Learn 2–4 provisional general principles for focused tracking and delayed bullet avoidance. For each current attached frame estimate the SMALL BOSS x/y yourself visually. Never treat your previous estimates as truth. Explain qualitative drift/turn evidence; do not derive an exact boss formula, seed schedule, period/timing lookup, or episode-time action script. The player would face roughly2.7s observation-to-application delay in a later evaluation, whereas this human demonstration had ordinary immediate feedback. Consider whether short move/hold action chunks might bridge that delay while preserving a clear whole path; this is a hypothesis to test, not a claim that the human solved delayed control. Preserve useful shooting, avoid excessive leading and overshooting, prioritize bullets that will cross the delayed path. A fixed human action is not uniquely correct. Do not output playable actions or timestamped action recipes.
Return only the requested schema: current-frame boss estimates, qualitative motion notes, 2–4 general policy hypotheses each with evidence and limitation/test, a chunking hypothesis, and limitations. The final batch should synthesize the accumulated evidence into2–4 concise transferable priors. These priors will be tested on different images/new episodes; this training run cannot be called held-out success.
'''


def study(bundle_dir:Path,output:Path,suite:Path):
    from .subscription import SubscriptionClient
    bundle=load(bundle_dir/'bundle.json');output.mkdir(parents=True,exist_ok=False)
    schema=learning_schema();save(output/'schema.json',schema)
    client=SubscriptionClient(suite,output/'client',schema,lean=False,aggressive=True)
    estimates=[];notes=[];previous_hypotheses=[];chunking=None;results=[]
    try:
        for batch in bundle['batches']:
            visible={'batch_index':batch['index'],'last_batch':batch['index']==len(bundle['batches'])-1,
                     'frames':[{'frame':i['frame'],'target_frame':i['target_frame'],'held':i['held']} for i in batch['images']],
                     'human_summary':bundle['human_summary'],
                     'past_completed_demonstration_controls':batch['past_completed_demonstration_controls'],
                     'your_own_previous_boss_estimates':estimates,'your_own_previous_notes':notes,
                     'your_own_previous_policy_hypotheses':previous_hypotheses,'your_own_previous_chunking_hypothesis':chunking}
            prompt=INSTRUCTION+'\nObserved training data and your own previous output:\n'+json.dumps(visible,ensure_ascii=False)
            call=output/f"batch_{batch['index']:02d}";call.mkdir();(call/'prompt.txt').write_text(prompt)
            images=[]
            for image in batch['images']:
                data=(bundle_dir/image['png']).read_bytes()
                if sha(data)!=image['sha256']:raise ValueError('Original image hash drift')
                images.append(data)
            response=client.act(prompt,images,call);answer=json.loads(response['answer'])
            expected={i['frame'] for i in batch['images']}
            if len(answer['boss_estimates'])!=len(expected) or {e['frame'] for e in answer['boss_estimates']}!=expected:raise ValueError('Estimate frames do not match current images')
            if response['meta'].get('model')!='gpt-6.1-sol':raise ValueError('Wrong model')
            estimates.extend(answer['boss_estimates']);notes=(notes+answer['motion_notes'])[-16:]
            previous_hypotheses=answer['policy_hypotheses'];chunking=answer['chunking_hypothesis']
            results.append({'batch':batch['index'],'prompt_sha256':sha(prompt.encode()),
                            'image_sha256s':[i['sha256'] for i in batch['images']],'response':response})
            save(output/'completed_prefix.json',results)
    finally:client.close()
    save(output/'learned_prior.json',{'kind':'provisional_sol_visual_demo_prior','training_source':bundle['source_run'],
         'model':'gpt-6.1-sol','effort':'low','native_envelope':'aggressive','turns':len(results),
         'not_heldout_or_game_success':True,'policy_hypotheses':previous_hypotheses,'chunking_hypothesis':chunking,
         'limitations':answer['limitations'],'self_reported_visual_estimates':estimates})
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('source',type=Path);a.add_argument('output',type=Path)
    a=sub.add_parser('study');a.add_argument('bundle',type=Path);a.add_argument('output',type=Path);a.add_argument('--suite',type=Path,required=True)
    a=p.parse_args()
    if a.command=='prepare':prepare(a.source,a.output)
    else:study(a.bundle,a.output,a.suite)

if __name__=='__main__':main()
