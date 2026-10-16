set -eu
PY=/home/ubuntu/lzj/envs/coding-agent-suite/bin/python
RUNTIME=/home/ubuntu/wzh/expts-sol/runtime/case-prompt-search-20261015
$PY - <<'WAIT'
from pathlib import Path
import time
while True:
    p=Path('/proc/3457958')
    try:
        state=(p/'stat').read_text().split(') ',1)[1].split()[0]
        cmd=(p/'cmdline').read_bytes()
        if state in ('Z','X') or b'compare_food_policies.py' not in cmd:break
    except FileNotFoundError:break
    time.sleep(10)
WAIT
$PY - <<'GATE'
from pathlib import Path
import json
p=Path('/home/ubuntu/wzh/expts-sol/results/asterix/food-sequence-v28-v33-full20-20261015')
f=p/'summary.json'
if not f.exists():
    (p/'confirmation_gate.json').write_text(json.dumps({'continue':False,'reason':'Missing final comparison summary'})+'\n')
    raise SystemExit(2)
s=json.loads(f.read_text());a=s['episodes']
if s['status']!='complete' or len(a)!=6:
    (p/'confirmation_gate.json').write_text(json.dumps({'continue':False,'reason':'Incomplete full comparison; no extrapolation'})+'\n')
    raise SystemExit(2)
b={x['seed']:x for x in a if x['policy']=='food_route_v28'}
c={x['seed']:x for x in a if x['policy']=='food_route_v33'}
assert set(b)==set(c)=={2,5,6}
score={v:sum(rows[s]['score'] for s in rows) for v,rows in [('V28',b),('V33',c)]}
lives={v:[rows[s]['lives'] for s in (2,5,6)] for v,rows in [('V28',b),('V33',c)]}
passed=score['V33']>score['V28'] and all(c[s]['lives']>=b[s]['lives'] and c[s]['frames']==1200 for s in b)
(p/'confirmation_gate.json').write_text(json.dumps({'continue':passed,'score_sums':score,'remaining_lives_seeds_2_5_6':lives,'criterion':'Higher aggregate food score; all candidate games reach20s; no extra life loss per seed. Research screen only, no automatic promotion.'},indent=2)+'\n')
print('FULL_CONFIRMATION_SCREEN',score,lives,passed,flush=True)
if not passed:raise SystemExit(2)
r=Path('/home/ubuntu/wzh/expts-sol/runtime/case-prompt-search-20261015')
tasks=json.loads((r/'food_sequence_v33_paired_tasks.json').read_text());assert len(tasks)==260
for t in tasks:
    t['repeat']+=5
    t['pair_id']=t['case_id']+'-'+str(t['repeat'])
(r/'food_sequence_v33_confirmation_tasks.json').write_text(json.dumps(tasks))
GATE
cd "$RUNTIME"
$PY evaluate_case_prompts_v2.py --source /home/ubuntu/wzh/expts-sol/results/asterix/iterative-intercept-20261014/source --suite /home/ubuntu/lzj/coding-agent-suite --tasks food_sequence_v33_confirmation_tasks.json --output /home/ubuntu/wzh/expts-sol/results/asterix/food-sequence-v33-independent-confirmation-20261015 --workers 8 --quota-stop-percent 80 --minimal-system-file minimal_system.txt
