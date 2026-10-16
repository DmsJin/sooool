"""Select from complete paired development results, then test execution delay.
Subscription only; this process never opens the paid API or accesses credentials.
"""
import argparse,json,subprocess,time
from pathlib import Path

def predecessor_running(pid,round_names):
    path=Path(f'/proc/{pid}/cmdline')
    try:cmd=path.read_bytes()
    except FileNotFoundError:cmd=b''
    if b'defer-hold-v1.py' in cmd or (b'run_round.py' in cmd and any(name.encode() in cmd for name in round_names)):return True
    # Also protect against an orphaned child if its wrapper was terminated.
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:cmd=path.read_bytes()
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
        if b'run_round.py' in cmd and any(name.encode() in cmd for name in round_names):return True
    return False

def select(report):
    groups={}
    for arm in ('baseline','hold'):
        summaries=[]
        for seed in (2,5):
            row=report['jobs'][f'{arm}-seed{seed}']
            if row['status']!='complete' or not row['summary']['finished']:
                raise ValueError('Selection needs every paired development episode complete')
            summaries.append(row['summary'])
        groups[arm]={'wins':sum(s['winner']=='A' for s in summaries),
                     'mean_point_share':sum(s['scores']['A']/sum(s['scores'].values()) for s in summaries)/2}
    rank=lambda arm:(groups[arm]['wins'],groups[arm]['mean_point_share'])
    selected='hold' if rank('hold')>rank('baseline') else 'baseline'
    return selected,groups

def run(a):
    round_names=['paired-hold-round-v1',*a.additional_round]
    while predecessor_running(a.predecessor,round_names):time.sleep(20)
    report={'jobs':{}}
    for name in round_names:
        part=json.loads((a.runtime/name/'results.json').read_text())
        for job,row in part['jobs'].items():
            previous=report['jobs'].get(job)
            if previous and previous['status']=='complete' and row['status']=='complete':
                if previous['summary']['digest']!=row['summary']['digest']:
                    raise ValueError('Duplicate completed job has different native state')
            report['jobs'][job]=row
    selected,groups=select(report)
    mode='geometry_stable_early_fast'+('_hold' if selected=='hold' else '')
    plan={'profile':str(a.runtime/'profile-menu-serial-v1/profile.json'),
          'parallel_episodes':2,'gap_s':2,'delay_scale':1.25,
          'jobs':[{'name':'executor-selected-seed6','seed':6,'variant':mode+'_executor_chunk'},
                  {'name':'executor-feedback-seed6','seed':6,'variant':mode+'_feedback_executor_chunk'}],
          'selection':{'from':round_names,'selected':selected,'development_metrics':groups,'tie_break':'baseline'},
          'scope':'Development paired seed6; measured local native lowering blocks controller; API samples scaled 1.25 for sensitivity, not a new measured profile; feedback changes prompt; not held-out or real API validation',
          'paid_api_calls':0}
    path=a.runtime/'paired-executor-plan-v1.json';path.write_text(json.dumps(plan,indent=2))
    print('SELECTED',json.dumps(plan['selection']),flush=True)
    child=subprocess.run([a.python,str(Path(__file__).with_name('run_round.py')),'--plan',str(path),'--output',str(a.runtime/'paired-executor-round-v1'),'--python',a.python])
    print('ROUND_TERMINAL',child.returncode,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--predecessor',type=int,required=True);p.add_argument('--additional-round',nargs='*',default=[]);p.add_argument('--python',default='/home/ubuntu/wzh/sooool-runtime/venv/bin/python');run(p.parse_args())
