"""Deterministic readiness/terminal lifecycle checks; no API or native games."""
import concurrent.futures as cf
import json
import threading
from stream_dispatch import ActionRequests


def run():
    logs=[];release=threading.Event()
    def delayed(items,on_ready,choice_count):
        on_ready({'status':'action_ready','answer':'{"choice":0}','choice':0})
        assert release.wait(2), 'test tail was not released'
        return {'status':'completed','error':None,'answer':'{"choice":0}','usage':{'output_tokens':5}}
    with cf.ThreadPoolExecutor(max_workers=1) as pool:
        manager=ActionRequests(pool,delayed,1,lambda r,m:logs.append((r,m)))
        request=manager.submit([],{'seq':0,'phase':'running'},1)
        request['ready'].result(timeout=1)
        delivered=list(manager.ready());assert len(delivered)==1
        assert not request['completion'].done(),'Action waited for terminal'
        assert manager.in_flight==1 and not logs,'Early readiness released capacity/logged a false terminal'
        try:manager.submit([],{},1)
        except RuntimeError:pass
        else:raise AssertionError('Draining stream did not occupy capacity')
        request['meta']['visible_step']=123
        manager.collect();assert manager.in_flight==1
        release.set();request['completion'].result(timeout=1);manager.collect()
        assert manager.in_flight==0 and len(logs)==1 and logs[0][1]['visible_step']==123
        assert logs[0][0]['usage']['output_tokens']==5

    def immediate(items,on_ready,choice_count):
        on_ready({'status':'action_ready','answer':'{"choice":0}'})
        return {'status':'completed','error':None}
    with cf.ThreadPoolExecutor(max_workers=1) as pool:
        logs=[];manager=ActionRequests(pool,immediate,1,lambda r,m:logs.append((r,m)))
        request=manager.submit([],{'phase':'running'},1);request['completion'].result(timeout=1)
        manager.collect();assert manager.in_flight==1 and not logs,'Collected an unconsumed successful action'
        assert len(list(manager.ready()))==1
        manager.collect();assert manager.in_flight==0 and len(logs)==1
        request=manager.submit([],{'phase':'running'},1)
        manager.drain('dropped_review');assert len(logs)==2 and logs[-1][1]['phase']=='dropped_review'
        assert not request['consumed'],'Review executed a leftover action'

    release=threading.Event();logs=[]
    def late_failure(items,on_ready,choice_count):
        on_ready({'status':'action_ready','answer':'{"choice":0}'})
        assert release.wait(2)
        return {'status':'failed','error':'server failed after text','usage':{'output_tokens':5}}
    with cf.ThreadPoolExecutor(max_workers=1) as pool:
        manager=ActionRequests(pool,late_failure,1,lambda r,m:logs.append((r,m)))
        request=manager.submit([],{'phase':'running'},1);request['ready'].result(timeout=1)
        assert len(list(manager.ready()))==1 and not request['completion'].done()
        release.set()
        try:manager.drain('ending')
        except RuntimeError:pass
        else:raise AssertionError('Late terminal failure became success')
        assert manager.in_flight==0 and len(logs)==1 and logs[0][0]['status']=='failed'

    def known_failure(items,on_ready,choice_count):
        on_ready({'status':'action_ready','answer':'{"choice":0}'})
        return {'status':'failed','error':'already known failure'}
    with cf.ThreadPoolExecutor(max_workers=1) as pool:
        logs=[];manager=ActionRequests(pool,known_failure,1,lambda r,m:logs.append((r,m)))
        request=manager.submit([],{'phase':'running'},1);request['completion'].result(timeout=1)
        try:list(manager.ready())
        except RuntimeError:pass
        else:raise AssertionError('Delivered an action despite known failure')
        assert not request['consumed'] and manager.in_flight==0 and len(logs)==1

    report={'scope':'Deterministic offline streamed-action lifecycle, not paid/native performance',
            'action_delivered_before_terminal':True,'draining_stream_retains_capacity':True,
            'usage_logged_only_after_terminal':True,'finished_unconsumed_action_preserved':True,
            'review_discards_action_and_drains':True,'late_failure_rejects_success':True,
            'known_failure_prevents_delivery':True,'api_calls':0}
    print(json.dumps(report));return report

if __name__=='__main__':run()
