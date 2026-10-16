"""Fixed public-history serve branches; no model calls or GPT performance claims.

Use after frozen rounds drain. A controlled toss tick isolates time alignment;
measured planner wall time is reported separately and does not certify realtime
execution. All simulated motion uses the unchanged native high-action layer.
"""
import argparse,hashlib,json,math,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MUJOCO_GL','egl')
from core.episode import load_plugin,header_cfg
from core.sport import parse_action,UNIT_OVER,FINISHED

def serving_chunk(events,seq=None):
    issued={r['seq']:r for r in events if r['ev']=='model_issued'}
    for i,r in enumerate(events):
        if r['ev']!='model_visible' or (seq is not None and r['seq']!=seq):continue
        option=next(o for o in issued[r['seq']]['options'] if o['id']==json.loads(r['answer'])['choice'])
        if option['kind']!='serve_bundle':continue
        # Visible choices can be discarded as stale. Associate both effects by
        # sequence, not the next toss of an unrelated point.
        effects=[(j,e) for j,e in enumerate(events[i+1:],i+1) if e['ev']=='effect' and e['seq']==r['seq']]
        windup=next(((j,e) for j,e in effects if 'T_from_now' in e.get('info',{}) and 'command' in e.get('result',{})),None)
        tossed=next(((j,e) for j,e in effects if 'projected_at_step' in e.get('result',{})),None)
        if windup is None or tossed is None:continue
        wi,effect=windup;ti,toss_effect=tossed
        if ti<=wi or any(e['ev']=='world_events' and any(p['kind']=='point' for p in e['events']) for e in events[wi+1:ti]):continue
        toss=events[ti-1]
        assert toss['ev']=='cmd' and toss['cmd'].get('type')=='toss' and toss['k']==toss_effect['k'],'Missing adjacent toss command'
        return option,effect,toss
    raise ValueError('No executed requested GPT-selected serving chunk')

def run(a):
    a.output.mkdir(parents=True,exist_ok=False)
    sport=load_plugin(str(ROOT/'sports/tabletennis/plugin.py'));layer=sport.action_layer('high');results=[]
    for source in a.source:
        history=source/'episode.jsonl';events=[json.loads(l) for l in history.read_text().splitlines()]
        cfg=header_cfg(next(r for r in events if r['ev']=='header'));assert cfg.format=='match','Diagnostic supports match only'
        option,effect,toss=serving_chunk(events,a.seq)
        start=effect['k'];original_gap=option['actions'][1]['after_steps'];observed_gap=toss['k']-start
        assert original_gap==10,'This diagnostic compares the original10tick chunk'
        for name,gap,shift in [('observed_original',observed_gap,0),('ideal_original',10,0),('windup30',30,.2)]:
            m=sport.build(cfg);timeline={}
            for r in events:
                if r['ev'] in ('cmd','resume') and r['k']<start:timeline.setdefault(r['k'],[]).append(r)
            while m.k<start:
                for r in timeline.get(m.k,[]):
                    if r['ev']=='cmd':m.apply(r['seat'],r['cmd'])
                    else:m.resume()
                m.step()
            own=m.observe('A');assert own['you_serve'] and own['serve']['phase']=='open'
            deadline_step=start+round(own['serve']['deadline_in_s']/m.dt)
            body=dict(option['actions'][0]['action']);body['t']=round(body['t']+shift,4)
            tick=time.monotonic();parsed=parse_action(layer,'A',body,m,{})
            low,info=layer.lower('A',parsed,None,m);m.apply('A',low);planner_s=time.monotonic()-tick
            while m.k<start+gap and m.phase().state not in (UNIT_OVER,FINISHED):m.step()
            assert m.k==start+gap,'Point ended before prescribed toss'
            tossbody=dict(option['actions'][1]['action']);parsed=parse_action(layer,'A',tossbody,m,{})
            low,toss_info=layer.lower('A',parsed,None,m);toss_result=m.apply('A',low)
            projected_step=toss_result['projected_at_step']
            tf=option['actions'][0]['action']['t']-(original_gap+10)*m.dt
            nominal_error=body['t']-((projected_step-start)*m.dt+tf)
            while m.k<start+500 and m.phase().state not in (UNIT_OVER,FINISHED):m.step()
            own=m.observe('A');planner_ticks=math.ceil(planner_s/(cfg.slowdown*m.dt))
            result={'scope':'Controlled native timing branch, passive after serving; no GPT calls; planner stall not imposed on toss clock',
                    'source':str(source),'history_sha256':hashlib.sha256(history.read_bytes()).hexdigest(),'seed':cfg.seed,
                    'seq':effect['seq'],'windup_step':start,'test':name,'original_observed_gap_ticks':observed_gap,
                    'test_gap_ticks':gap,'contact_in_s':body['t'],'planner_wall_s':planner_s,
                    'planner_equivalent_block_ticks':planner_ticks,'planner_fits_prescribed_gap':planner_ticks<=gap,
                    'toss_deadline_step':deadline_step,'toss_before_deadline':start+gap<deadline_step,
                    'planned_contact_step':start+int(info['n_swing_steps_available']),
                    'native_projected_at_step':projected_step,'nominal_contact_error_game_s':round(nominal_error,6),
                    'end_step':m.k,'scores':m.scores(),
                    'points':own['points'],'shots':own.get('shots'),'native_digest':m.state_digest(),
                    'windup_feedback':{k:info.get(k) for k in ('blade_error_m','normal_error_deg','speed_scale','stroke')},
                    'toss_lowering_feedback':toss_info,'toss_apply_feedback':toss_result,'paid_api_calls':0,'model_calls':0}
            results.append(result);(a.output/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,nargs='+',required=True);p.add_argument('--seq',type=int);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
