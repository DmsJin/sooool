"""Serial paired clocks on exact native camera/menu inputs; dry-run by default.

One streamed call measures both first usable action and full completion. No game
runs here. Keep every attempted row; never discard a slow call to improve numbers.
"""
import argparse,getpass,json,statistics
from pathlib import Path
from paid import API,Budget
from profile_matched import prepare


def stats(values):
    if not values:return None
    values=sorted(values)
    return {'n':len(values),'min_s':values[0],'mean_s':statistics.mean(values),
            'p50_s':statistics.median(values),'p95_s':values[(95*len(values)+99)//100-1]}


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--calls',type=int,default=12);p.add_argument('--run-paid',action='store_true');a=p.parse_args()
    if not 6<=a.calls<=24:raise ValueError('Choose six to24 serial observations')
    samples,source=prepare(a.source,a.calls);a.output.mkdir(parents=True,exist_ok=False)
    plan={'scope':'Serial same-call paired clocks; exact existing game prompts/cameras, no realtime gameplay claim',
          'model':'gpt-6.1-sol','service_tier':'ultrafast','concurrency':1,'source_digest':source['digest'],
          'variant':source['variant'],'planned_calls':len(samples),
          'samples':[{k:s[k] for k in ['seq','kind','image_sha256','prompt_sha256']} for s in samples]}
    (a.output/'plan.json').write_text(json.dumps(plan,indent=2))
    if not a.run_paid:print(json.dumps({'paid_calls':0,**plan}));return
    key=getpass.getpass('API key (memory only): ');budget=Budget(a.ledger);api=API(key,budget,'profiling',5);key=None;rows=[]
    try:
        for sample in samples:
            captured=[]
            items=[{'role':'user','content':[{'type':'input_text','text':sample['prompt']},
                   {'type':'input_image','detail':'high','image_url':'data:image/png;base64,'+sample['image_b64']}]}]
            count=api.count(items)
            row=api.call(items,count=count,choice_count=len(sample['options']),on_ready=captured.append)
            try:
                obj=json.loads(row['answer']);valid=set(obj)=={'choice'} and type(obj['choice'])==int and 0<=obj['choice']<len(sample['options'])
            except (ValueError,KeyError,TypeError):valid=False
            row.update(seq=sample['seq'],source_kind=sample['kind'],action_contract_valid=valid,
                       readiness_notifications=len(captured),readiness=captured[0] if captured else None,concurrency=1)
            rows.append(row)
            with (a.output/'requests.jsonl').open('a') as out:out.write(json.dumps(row)+'\n')
            print(json.dumps({k:row.get(k) for k in ['seq','status','action_ready_s','request_s','stream_tail_s','cost_usd','error']}),flush=True)
            if row['error'] or row['status']!='completed':break
    finally:api.http.close()
    paired=[r for r in rows if r['status']=='completed' and not r['error'] and r['action_contract_valid'] and r['readiness_notifications']==1 and r.get('action_ready_s') is not None]
    ready=[r['action_ready_s'] for r in paired];full=[r['request_s'] for r in paired];tails=[b-a for a,b in zip(ready,full)]
    usable=len(paired)==len(rows)==len(samples)
    report={'scope':plan['scope'],'model':plan['model'],'service_tier':plan['service_tier'],'concurrency':1,
            'attempts':len(rows),'valid_paired_calls':len(paired),'planned_calls':len(samples),'usable_for_simulation':usable,
            'action_ready':stats(ready),'full_response':stats(full),'paired_tail_saved':stats(tails),
            'cost_usd':sum(r['cost_usd'] for r in rows),'source_digest':source['digest'],'variant':source['variant'],
            'failed_or_unpaired_sequences':[r['seq'] for r in rows if r not in paired],
            'all_wire_completed_request_s':[r['request_s'] for r in rows if r['status']=='completed'],
            'latency_clock':'first complete legal JSON action; terminal identity and usage validated before profile acceptance',
            'delays_s':ready if usable else [],'p50_s':statistics.median(ready) if usable else None,
            'p95_s':stats(ready)['p95_s'] if usable else None,
            'budget':budget.update(lambda d:{'used_usd':d['used_usd'],'pending':len(d['pending']),'blocked':d['blocked']})}
    (a.output/'profile.json').write_text(json.dumps(report,indent=2));print('SUMMARY',json.dumps(report),flush=True)

if __name__=='__main__':main()
