"""Native timing diagnostic with fixed choices, never a GPT game result.
Checks that blocked controller work waits while physics advances, and that cached
prefix restoration reproduces the original native trajectory and camera hashes.
"""
import argparse,concurrent.futures as cf,json,sys
from pathlib import Path
from types import SimpleNamespace
import simulate

class FixedPool:
    requests=0
    def __init__(self,*args,**kwargs):pass
    def submit(self,text,image,directory):
        type(self).requests+=1
        options=json.loads(text.split('\nCANDIDATES ')[1]);choice=0
        for kind in ('serve_bundle','move','act'):
            match=next((o for o in options if o['kind']==kind),None)
            if match is not None:choice=match['id'];break
        directory.mkdir()
        (directory/'input.json').write_text(json.dumps({'params':{'input':[{'text':text}]}}))
        result={'answer':json.dumps({'choice':choice}),'scope':'fixed native timing diagnostic, no model'}
        (directory/'result.json').write_text(json.dumps(result))
        future=cf.Future();future.set_result(result);return future
    def close(self):pass

def run(output):
    output.mkdir(parents=True,exist_ok=False)
    profile=output/'synthetic-test-profile.json'
    profile.write_text(json.dumps({'delays_s':[.2],'p50_s':.2,'p95_s':.2,'scope':'synthetic timing-test fixture, not measured API'}))
    simulate.Pool=FixedPool
    args=dict(profile=profile,seed=2,level=1,slowdown=10,variant='geometry_stable_early_fast_executor_chunk',workers=1,capacity=8,stride=2,max_steps=450,delay_scale=1)
    simulate.run(SimpleNamespace(**args,output=output/'first',resume_from=None))
    rows=[json.loads(l) for l in (output/'first/episode.jsonl').read_text().splitlines()]
    blocks=[r for r in rows if r['ev']=='execution_block'];assert blocks
    gated_events={'model_issued','model_visible','cmd'}
    advanced=0;late=0
    for index,block in enumerate(rows):
        if block['ev']!='execution_block':continue
        for row in rows[index+1:]:
            if row.get('k',block['k'])>=block['until'] or row['ev']=='resume':break
            assert row['ev'] not in gated_events,(block,row)
        advanced+=max(0,block['until']-block['k'])
    late=sum(r['k']>r['due'] for r in rows if r['ev']=='model_visible')
    assert advanced>0 and late>0
    first_requests=FixedPool.requests
    simulate.run(SimpleNamespace(**args,output=output/'restored',resume_from=output/'first'))
    original=json.loads((output/'first/summary.json').read_text());restored=json.loads((output/'restored/summary.json').read_text())
    for key in ('digest','k','scores','calls'):assert original[key]==restored[key],key
    assert FixedPool.requests==first_requests,'Cached replay invoked a fresh decision'
    original_blocks=[(r['k'],r['until'],r['elapsed_wall_s']) for r in blocks]
    restored_blocks=[(r['k'],r['until'],r['elapsed_wall_s']) for r in map(json.loads,(output/'restored/episode.jsonl').read_text().splitlines()) if r['ev']=='execution_block']
    assert original_blocks==restored_blocks
    report={'scope':'fixed native controller timing diagnostic, not GPT performance','paid_api_calls':0,'model_calls':0,'execution_blocks':len(blocks),'blocked_ticks':advanced,'responses_delayed_past_sampled_due':late,'native_digest_restored':True,'all_cached_images_and_prompts_matched':True,'fresh_decisions_during_restore':0}
    (output/'check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)
