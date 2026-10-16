"""Loopback SSE through unchanged native proxy; no external API or game calls."""
import concurrent.futures as cf
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,os,socket,subprocess,sys,tempfile,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from paid import API,Budget,MODEL,TIER
from stream_dispatch import ActionRequests
from core.metering.think_clock import ThinkClock


def run():
    release=threading.Event();upstream_done=threading.Event()
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert data['stream'] and data['model']==MODEL and data['service_tier']==TIER
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            def send(event):
                self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode());self.wfile.flush()
            send({'type':'response.created','response':{'id':'resp_loopback','model':MODEL,'service_tier':TIER,'status':'in_progress'}})
            for delta in ['{"choice":','1','}']:
                send({'type':'response.output_text.delta','delta':delta,'output_index':0,'content_index':0})
            assert release.wait(8),'Client waited for terminal before delivering action'
            send({'type':'response.completed','response':{'id':'resp_loopback','model':MODEL,'service_tier':TIER,
                  'status':'completed','output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'{"choice":1}'}]}],
                  'usage':{'input_tokens':100,'output_tokens':10,'total_tokens':110,'input_tokens_details':{'cached_tokens':0}}}})
            upstream_done.set()
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
    thread=threading.Thread(target=upstream.serve_forever,daemon=True);thread.start()
    with tempfile.TemporaryDirectory(prefix='sooool-stream-proxy-') as temporary:
        output=Path(temporary)
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        env={**os.environ,'OPENROUTER_API_KEY':'[REDACTED]','THINK_MODEL':MODEL,
             'THINK_UPSTREAM':'http://127.0.0.1:'+str(upstream.server_port),'THINK_OPENAI_ROUTE':'openrouter',
             'THINK_CLIENT_HOST':'localhost','THINK_USAGE_FILE':str(output/'usage.json'),
             'THINK_CALLS_FILE':str(output/'calls.jsonl'),'RCB_ACT_RULE':'program','RCB_PLAYER_MODE':'model'}
        proxy_log=(output/'proxy.log').open('w')
        proxy=subprocess.Popen([sys.executable,str(ROOT/'players/metering/think_proxy.py'),str(port)],env=env,stdout=proxy_log,stderr=subprocess.STDOUT)
        api=None
        try:
            deadline=time.monotonic()+5
            while True:
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                except OSError:
                    if proxy.poll() is not None or time.monotonic()>deadline:raise RuntimeError((output/'proxy.log').read_text())
                    time.sleep(.01)
            budget=Budget(output/'fake-budget.json');api=API('loopback-fixture-not-a-real-key',budget,'profiling',5,endpoint=f'http://127.0.0.1:{port}/v1/responses')
            rows=[]
            with cf.ThreadPoolExecutor(max_workers=1) as pool:
                manager=ActionRequests(pool,lambda items,**kw:api.call(items,count=200,**kw),1,lambda r,m:rows.append((r,m)))
                request=manager.submit([{'role':'user','content':[{'type':'input_text','text':'Loopback action fixture'}]}],{'phase':'running','seq':0},2)
                request['ready'].result(timeout=5)
                actions=list(manager.ready());assert len(actions)==1 and actions[0][1]['choice']==1
                assert not upstream_done.is_set() and not request['completion'].done()
                pending=budget.update(lambda d:len(d['pending']));assert pending==1
                # This is the unchanged native program-act meter, not oracle mode.
                previous=os.environ.get('RCB_ACT_RULE');os.environ['RCB_ACT_RULE']='program'
                try:assert ThinkClock(usage_file=str(output/'usage.json'),mode='model').decided_by_model()
                finally:
                    if previous is None:os.environ.pop('RCB_ACT_RULE',None)
                    else:os.environ['RCB_ACT_RULE']=previous
                release.set();request['completion'].result(timeout=5);manager.collect()
                assert len(rows)==1 and rows[0][0]['status']=='completed' and not rows[0][0]['error']
                ledger=budget.update(lambda d:d.copy());assert not ledger['pending'] and not ledger['blocked'] and ledger['used_usd']>0
            deadline=time.monotonic()+2
            while True:
                meter=json.loads((output/'usage.json').read_text())
                if meter['model_calls_completed']==1 and meter['in_flight']==0:break
                if time.monotonic()>deadline:raise AssertionError(meter)
                time.sleep(.01)
            report={'scope':'Loopback SSE fixture through unchanged native proxy and program meter; no real API/game performance claim',
                    'action_delivered_before_upstream_terminal':True,'reservation_retained_at_delivery':True,
                    'native_model_program_gate_permitted_inflight_action':True,'native_meter_completed_calls':1,
                    'terminal_usage_settled':True,'external_api_calls':0}
            print(json.dumps(report));return report
        finally:
            release.set()
            if api is not None:api.http.close()
            proxy.terminate()
            try:proxy.wait(timeout=3)
            except subprocess.TimeoutExpired:proxy.kill();proxy.wait()
            proxy_log.close();upstream.shutdown();upstream.server_close()

if __name__=='__main__':run()
