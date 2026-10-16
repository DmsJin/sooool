from pathlib import Path
import json
r=Path('/home/ubuntu/wzh/expts-sol/runtime/case-prompt-search-20261015');p=r/'food-sequence-actual-probe-v34'
b=(p/'food_route_v28.txt').read_text().strip();c=(p/'food_route_v34.txt').read_text().strip();tasks=[]
a=json.loads((r/'far_food_v28_paired_tasks.json').read_text())
a += json.loads((r/'food-sequence-handoff-inputs/tasks.json').read_text())
selected={'C05b','C06b','C10b','C12a','C12b','C18a','C18b'}
for t in a:
 if t['repeat'] or t['case_id'] not in selected or b not in t['prompt']:continue
 for v,s in [('probe_v28',b),('probe_v34',c)]:
  for rep in range(3):tasks.append(dict(t,variant=v,prompt=t['prompt'].replace(b,s),repeat=rep,pair_id=t['case_id']+'-'+str(rep)))
assert len(tasks)==42
assert len({(t['variant'],t['case_id'],t['repeat']) for t in tasks})==42
(p/'focus_tasks.json').write_text(json.dumps(tasks))
