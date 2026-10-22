"""Real API play through the unmodified native clock and model meter.

Credentials remain in controller/proxy process memory. No oracle exemption.
No official-Harbor claim: this is a local native-protocol research validation.
"""
import argparse
import concurrent.futures as cf
import getpass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import requests

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from paid import API,Budget
from wait_watch import make_watch,wake_reason
from core.client import Seat,wait_for

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--profile',type=Path,required=True)
    ap.add_argument('--ledger',type=Path,required=True);ap.add_argument('--seed',type=int,default=101)
    ap.add_argument('--level',type=int,default=1);ap.add_argument('--slowdown',type=float,default=10)
    ap.add_argument('--variant',default='geometry_chunk');ap.add_argument('--capacity',type=int,default=8)
    ap.add_argument('--stride',type=int,default=10);ap.add_argument('--game-port',type=int,default=18121)
    ap.add_argument('--proxy-port',type=int,default=18190);ap.add_argument('--stage-ceiling',type=float,default=19)
    ap.add_argument('--run-paid',action='store_true')
    a=ap.parse_args()
    if not a.run_paid:
        print(json.dumps({'model':'gpt-6.1-sol','tier':'ultrafast','meter':'native think_proxy; model mode; program act rule',
                          'slowdown':a.slowdown,'capacity':a.capacity,'paid_calls':0}));return
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'source').mkdir();(a.output/'observations').mkdir();(a.output/'inputs').mkdir()
    for path in Path(__file__).parent.glob('*.py'):
        raw=path.read_bytes();(a.output/'source'/path.name).write_bytes(raw)
    (a.output/'profile.json').write_bytes(a.profile.read_bytes())
    key=getpass.getpass('API key (memory only): ')
    budget=Budget(a.ledger);profile=json.loads(a.profile.read_text())
    for port in (a.game_port,a.proxy_port):
        import socket
        with socket.socket() as s:s.bind(('127.0.0.1',port))
    proxy_env={**os.environ,'OPENROUTER_API_KEY':key,'THINK_UPSTREAM':'https://api.openai.com',
               'THINK_OPENAI_ROUTE':'openrouter','THINK_MODEL':'gpt-6.1-sol','THINK_CLIENT_HOST':'localhost',
               'THINK_USAGE_FILE':str(a.output/'think_usage_A.json'),'THINK_CALLS_FILE':str(a.output/'think_calls_A.jsonl')}
    # OPENROUTER_API_KEY is the native generic proxy's legacy variable name.
    # THINK_UPSTREAM explicitly targets OpenAI; the actual model/tier are checked.
    proxy_log=(a.output/'proxy.log').open('w')
    proxy=subprocess.Popen([sys.executable,str(ROOT/'players/metering/think_proxy.py'),str(a.proxy_port)],cwd=ROOT,env=proxy_env,stdout=proxy_log,stderr=subprocess.STDOUT,start_new_session=True)
    proxy_env.pop('OPENROUTER_API_KEY',None)
    env={**os.environ,'MUJOCO_GL':'egl','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1',
         'RO_PLUGIN':str(ROOT/'sports/tabletennis/plugin.py'),'RO_SPORT':'tabletennis','RO_FORMAT':'match',
         'RO_SEATS':'A','RO_SEED':str(a.seed),'RO_LEVEL':str(a.level),'RO_SLOWDOWN':str(a.slowdown),
         'RCB_ACTION_LEVEL':'high','RCB_PLAY':'program','RCB_ACT_RULE':'program','RCB_PLAYER_MODE':'model',
         'RCB_DATA':str(a.output),'RCB_PORT':str(a.game_port),'RCB_RENDER_VIDEO':'0','START_TIMEOUT_S':'300','READY_TIMEOUT_S':'300'}
    server_log=(a.output/'server.log').open('w')
    server=subprocess.Popen([sys.executable,'-m','core.serve'],cwd=ROOT,env=env,stdout=server_log,stderr=subprocess.STDOUT,start_new_session=True)
    game=Seat('http://127.0.0.1:'+str(a.game_port),'A',timeout=180)
    endpoint='http://127.0.0.1:'+str(a.proxy_port)+'/v1/responses'
    api=API(key,budget,'validation',a.stage_ceiling,endpoint=endpoint)
    key=None
    requests_log=(a.output/'api_requests.jsonl').open('a')
    pool=cf.ThreadPoolExecutor(max_workers=a.capacity)
    pending=[];chunks=[];applied=[];seq=0;last=-1;wake=0;watch=None;failure=None;terminal_state={}
    timing={'p50_wall_s':profile['p50_s'],'p95_wall_s':profile['p95_s'],'slowdown':a.slowdown,
            'p50_game_s':profile['p50_s']/a.slowdown,'p95_game_s':profile['p95_s']/a.slowdown,
            'virtual_model_capacity':a.capacity,'observation_interval_game_s':a.stride*.01,'delay_source':'actual API, no sampling'}
    def call(items):
        # A conservative bound: prompt byte count <= 12k plus <8k image tokens
        # for the one 1920x720 eight-tile image. Avoid an extra remote token-count
        # request in the control loop. Actual usage settles the shared ledger.
        text=''.join(c.get('text','') for i in items for c in i['content'])
        if len(text.encode())>12000:raise RuntimeError('Input exceeds audited realtime reservation shape')
        client=API(api.http.headers['Authorization'][7:],budget,'validation',a.stage_ceiling,endpoint=endpoint)
        try:r=client.call(items,count=20000)
        finally:client.http.close()
        if r['error'] or r['status']!='completed':raise RuntimeError('Actual API request did not complete: '+str(r['error']))
        return r
    def settle(r,meta):
        requests_log.write(json.dumps({**meta,**r})+'\n');requests_log.flush()
    def items(text,image=None):
        content=[{'type':'input_text','text':text}]
        if image:content.append({'type':'input_image','detail':'high','image_url':'data:image/png;base64,'+image})
        return [{'role':'user','content':content}]
    def capture(name,text,image,options,state):
        import base64
        png=base64.b64decode(image);(a.output/'observations'/f'{name}.png').write_bytes(png)
        record={'prompt':text,'options':options,'obs_step':state['step'],'point':state.get('point')}
        (a.output/'inputs'/f'{name}.json').write_text(json.dumps(record))
    def execute(body,seen):
        reply=game.call('act',body)
        with (a.output/'controller_actions.jsonl').open('a') as f:f.write(json.dumps({'seen_step':seen,'action':body,'reply':reply})+'\n')
        if reply.get('http_status',200)>=500:raise RuntimeError('Native action service failure')
        if not reply.get('http_status'):
            effect=reply['took_effect']['step'];record={'step':effect,'action':body}
            if '_feedback_' in a.variant:
                from action_feedback import public_feedback
                record['execution_feedback']=public_feedback(reply['took_effect'].get('stroke',{}))
            applied.append(record);return effect
        return None
    try:
        spec=wait_for(game.base,'A',deadline_s=120)
        from core.episode import load_plugin
        load_plugin(str(ROOT/'sports/tabletennis/plugin.py')) # helper imports public player math; never builds a world
        sys.path.insert(0,str(a.output/'source'))
        from candidates import Candidates,menu_prompt
        menus=Candidates(spec,mode=a.variant)
        protocol={**vars(a),'model':'gpt-6.1-sol','service_tier':'ultrafast','actual_upstream':'https://api.openai.com',
                  'proxy_legacy_route_name':'openrouter','player_mode':'model','act_rule':'program','latency':'actual'}
        (a.output/'validation_protocol.json').write_text(json.dumps(protocol,default=str,indent=2))
        # A genuine model request establishes the native meter before start.
        view=game.call('observe',{});st=view['now'];v={'state':st,'observation':view['observation']}
        opts=menus.build(v,timing);text=menu_prompt(v,opts,timing,a.variant);capture('prepare',text,v['observation']['image_png_b64'],opts,st)
        r=call(items(text,v['observation']['image_png_b64']))
        settle(r,{'phase':'prepare','obs_step':st['step']})
        start_reply=game.call('start',{})
        (a.output/'native_start.json').write_text(json.dumps(start_reply))
        if start_reply.get('http_status') or 'error' in start_reply:raise RuntimeError('Native start refused: '+str(start_reply.get('error')))
        last_observed=-a.stride
        while True:
            st=game.call('status');step=st['step'];point=st.get('point')
            if st.get('done'):terminal_state=st;break
            if st['phase']=='review':
                for p in pending:settle(p['future'].result(),{'phase':'dropped_review','seq':p['seq'],'obs_step':p['step']})
                pending.clear();chunks.clear()
                review=call(items('Review the completed table-tennis point from this referee/own-state feedback. Return exactly JSON {"why":"brief observed cause","plan":"brief next-point adjustment"}.\n'+json.dumps(st)))
                settle(review,{'phase':'review','obs_step':step});rev=json.loads(review['answer'])
                game.call('ready',{'why':str(rev['why'])[:2000],'plan':str(rev['plan'])[:2000]})
                last_observed=-a.stride;wake=0;watch=None;continue
            if watch is not None and wake_reason(watch,st,step):
                watch=None;wake=step;last_observed=step-a.stride
            if st['phase']!='running':raise RuntimeError('Unexpected native phase: '+str(st['phase']))
            for c in [x for x in chunks if x['due']<=step]:
                chunks.remove(c)
                if c['point']==point:execute(c['action'],c['seen'])
            for p in [x for x in pending if x['future'].done()]:
                pending.remove(p);r=p['future'].result()
                # Earlier chunks or actions can block in the native planner while
                # the clock catches up. Re-read public state for each decision;
                # never reuse a pre-toss 'open' phase or a stale contact clock.
                st=game.call('status');step=st['step'];point=st.get('point')
                settle(r,{'phase':'running','seq':p['seq'],'obs_step':p['step'],'visible_step':step})
                if p['seq']<=last or p['point']!=point or st.get('world')!='running':continue
                choice=json.loads(r['answer'])['choice']
                if type(choice)!=int or not 0<=choice<len(p['options']):continue
                option=p['options'][choice];last=p['seq']
                if option['kind']=='wait':
                    wake=max(wake,step+option.get('wait_steps',0))
                    gate=make_watch(option,point,step)
                    if gate is not None:watch=gate
                    continue
                if option['kind']=='serve_bundle':
                    if chunks or st['serve']['phase']!='open':continue
                    first,*rest=option['actions'];effect=execute(first['action'],p['step'])
                    if effect is not None:chunks.extend({'due':effect+c['after_steps'],'action':c['action'],'point':point,'seen':p['step']} for c in rest)
                else:
                    body=dict(option['action'])
                    if 'contact_step' in option:
                        body['t']=(option['contact_step']-step)*.01
                        if body['t']<.04:continue
                    execute(body,p['step'])
            if watch is None and len(pending)<a.capacity and step>=wake and step-last_observed>=a.stride:
                reply=game.call('observe',{});v={'state':reply['now'],'observation':reply['observation']}
                if v['state']['world']!='running':continue
                v['state']['recent_applied']=applied[-4:]
                if chunks:v['state']['known_plan']=[{'due_step':c['due'],'action':c['action']} for c in chunks]
                opts=menus.build(v,timing);text=menu_prompt(v,opts,timing,a.variant)
                image=v['observation']['image_png_b64'];capture(f'{seq:05d}',text,image,opts,v['state']);f=pool.submit(call,items(text,image))
                pending.append({'future':f,'options':opts,'seq':seq,'step':v['state']['step'],'point':v['state']['point']})
                last_observed=v['state']['step'];seq+=1
                (a.output/'controller_progress.json').write_text(json.dumps({'step':last_observed,'score':v['state']['score'],'calls':seq,'pending':len(pending)}))
    except BaseException as exc:
        failure=type(exc).__name__+': '+str(exc)
        (a.output/'controller_failure.json').write_text(json.dumps({'error':failure}))
    finally:
        pool.shutdown(wait=True)
        for p in pending:
            try:settle(p['future'].result(),{'phase':'ending','seq':p['seq'],'obs_step':p['step']})
            except Exception:pass
        if server.poll() is None:
            server.send_signal(signal.SIGUSR1)
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                final=a.output/'final.json'
                if final.exists() and json.loads(final.read_text()).get('graded_ready'):break
                time.sleep(.5)
        for process in (server,proxy):
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait()
        api.http.close();requests_log.close();server_log.close();proxy_log.close()
        summary={'status':'completed' if terminal_state.get('done') and failure is None else 'incomplete',
                 'failure':failure,'terminal_state':terminal_state,'model_requests_issued':seq,
                 'cost_ledger':budget.update(lambda d:{'cumulative_usd':d['used_usd'],'stages':d.get('stages'),
                                                     'pending_reservations':len(d['pending'])})}
        (a.output/'validation_summary.json').write_text(json.dumps(summary,indent=2))
    if failure:raise RuntimeError(failure)
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
