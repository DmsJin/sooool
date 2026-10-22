"""Matched real subscription requests at concurrency 1/2/4; no live task scores."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import json
import queue
import statistics
import time
import numpy as np
from runtime.evaluation import recording
from .runner import POLICY, ROOT, freeze, write, save_report, parse_decision

SAMPLES=(0,8,19,30,38,49,61,67)


def stats(values):
    if not values:return None
    return {'n':len(values),'mean':statistics.mean(values),'p50':statistics.median(values),
            'p95':float(np.percentile(values,95)),'min':min(values),'max':max(values)}


def benchmark(output,source):
    from runtime.subscription import SubscriptionClient
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False);source=Path(source).resolve()
    config={'source_trial':str(source),'sample_calls':list(SAMPLES),'concurrency_levels':[1,2,4],
            'model':'gpt-6.1-sol','effort':'low','service_tier':'priority','actual_requests':24,
            'mode':'frozen public observations; no physics/action execution or handling scores'}
    freeze(out,config)
    manifest=json.loads((out/'manifest.json').read_text());manifest['mode']='actual_subscription_frozen_observation_latency_benchmark'
    manifest['oracle_actions']=False;manifest['handling_score']=None;write(out/'manifest.json',manifest)
    inputs=[]
    for number in SAMPLES:
        d=source/f'call-{number:03d}'/'model'
        prompt=(d/'prompt.txt').read_text();images=[(d/f'image_{i}.png').read_bytes() for i in range(3)]
        inputs.append((prompt,images))
    clients=[];rows=[];cohorts=[];error=None
    try:
        for i in range(4):
            clients.append(SubscriptionClient(output=out/f'worker-{i}',system=(POLICY/'system.txt').read_text(),
                output_schema=json.loads((POLICY/'action.schema.json').read_text()),service_tier='priority',
                auth_only_home=True,record_reasoning=False))
        # Same snapshots per block; reverse order in block two to expose warm/order effects.
        for block,levels in enumerate(((1,2,4),(4,2,1))):
            for concurrency in levels:
                cohort=out/f'block-{block}-c{concurrency}';cohort.mkdir()
                available=queue.Queue()
                for i in range(concurrency):available.put((i,clients[i]))
                def request(index):
                    worker,client=available.get();started=time.monotonic()
                    d=cohort/f'input-{index}';prompt,images=inputs[index]
                    try:
                        answer,meta=client.act(prompt,images,d)
                        finished=time.monotonic();valid=True
                        try:parse_decision(answer)
                        except (ValueError,TypeError):valid=False
                        return {'block':block,'concurrency':concurrency,'sample':SAMPLES[index],
                            'worker':worker,'started':started,'finished':finished,'wall_seconds':finished-started,
                            'native_wall_seconds':meta['wall_seconds'],'token_usage':meta['token_usage'],
                            'valid_chunk':valid,'output':str(d)}
                    finally:available.put((worker,client))
                started=time.monotonic()
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures=[pool.submit(request,i) for i in range(block*4,block*4+4)]
                    batch=[future.result() for future in as_completed(futures)]
                elapsed=time.monotonic()-started
                rows.extend(batch);cohorts.append({'block':block,'concurrency':concurrency,'calls':4,
                    'elapsed_s':elapsed,'amortized_reply_interval_s':elapsed/4})
                write(cohort/'report.json',{'requests':batch,'elapsed_s':elapsed})
                print(json.dumps({'block':block,'concurrency':concurrency,'latency':stats([r['wall_seconds'] for r in batch]),
                      'elapsed_s':elapsed,'amortized_reply_interval_s':elapsed/4}),flush=True)
    except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)}
    finally:
        for client in clients:client.close()
        summaries=[]
        for concurrency in (1,2,4):
            selected=[r for r in rows if r['concurrency']==concurrency]
            phase=[c for c in cohorts if c['concurrency']==concurrency]
            duration=sum(c['elapsed_s'] for c in phase)
            summaries.append({'concurrency':concurrency,'calls':len(selected),'request_latency_s':stats([r['wall_seconds'] for r in selected]),
                'cohort_elapsed_s':duration,'amortized_reply_interval_s':duration/len(selected) if selected else None,
                'valid_chunks':sum(r['valid_chunk'] for r in selected)})
        report={'kind':'actual_subscription_matched_snapshot_concurrency_benchmark','config':config,
            'actual_model_calls_completed':len(rows),'direct_api_calls':0,'cached_decision_replay':False,
            'physics_running':False,'handling_score':None,'summaries':summaries,'cohorts':cohorts,'requests':rows,'error':error}
        save_report(out,report)
    print(json.dumps({'output':str(out),'summaries':summaries,'error':error},indent=2),flush=True)
    if error:raise RuntimeError(str(error))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['latency'])
    p.add_argument('--output',type=Path,default=ROOT/'runs'/f'pcba-latency-{time.strftime("%Y%m%dT%H%M%S")}')
    p.add_argument('--provider',choices=['subscription'],default='subscription',help='Decision source (default: subscription)')
    p.add_argument('--source',type=Path,default=Path('runs/pcba-policy-fast-v1'))
    a=p.parse_args()
    with recording(a.output,game='pcba',command='latency',provider=a.provider,clock='none',detail_file='report.json'):
        benchmark(a.output,a.source)
