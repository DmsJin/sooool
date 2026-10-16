"""Prepare frozen observations; never pass original answers or labels to the model."""
from pathlib import Path
import base64
import hashlib
import json

ROOT=Path('/home/ubuntu/wzh/expts-sol/runtime/case-prompt-search-20261015')
HERE=ROOT/'food-sequence-empty-target-v35'
strategies={f'v{n}':(HERE/f'food_route_v{n}.txt').read_text().strip() for n in (28,33,35,36)}
templates={}
wanted={'C05b','C06b','C10b','C12a','C12b','C13a','C14a','C18a','C18b'}
source=json.loads((ROOT/'far_food_v28_paired_tasks.json').read_text())
source+=json.loads((ROOT/'food-sequence-handoff-inputs/tasks.json').read_text())
for task in source:
    if task['repeat']==0 and task['case_id'] in wanted and strategies['v28'] in task['prompt']:
        templates[task['case_id']]=(task['prompt'],strategies['v28'],task['images'])
review=json.loads((ROOT/'food-sequence-actual-probe-v34/seed2-first-death-rewind/observations.json').read_text())
restore=[]
for cid,frame in (('C19a',192),('C19b',204)):
    obs=next(o for o in review['observations'] if o['frame']==frame)
    images=[]
    for image in obs['model_images']:
        data=Path(image['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest()==image['sha256']
        images.append('data:image/png;base64,'+base64.b64encode(data).decode())
    templates[cid]=(obs['prompt'],strategies['v33'],images)
    restore.append({'case_id':cid,'seed':2,'frame':frame,'model_images':obs['model_images']})
assert len(templates)==11
tasks=[]
for variant,strategy in strategies.items():
    for cid,(prompt,old,images) in templates.items():
        assert prompt.count(old)==1
        for repeat in range(10 if cid.startswith('C19') else 3):
            tasks.append({'variant':variant,'case_id':cid,'repeat':repeat,'wrapper_profile':'minimal',
                'prompt':prompt.replace(old,strategy),'images':images,'pair_id':cid+'-'+str(repeat)})
assert len(tasks)==188 and len({(t['variant'],t['case_id'],t['repeat']) for t in tasks})==188
(HERE/'tasks.json').write_text(json.dumps(tasks))
(HERE/'restore_cases.json').write_text(json.dumps(restore,indent=2)+'\n')
(HERE/'diagnostic_notes.json').write_text(json.dumps({'new_cases':'C19a192/C19b204 from one seed2 event; correlated development observations, not independent scenes',
    'new_preference':'Stay in safe current row when no food/current-row threat; preferNOOP or horizontal recentering. Provisional diagnostic only; original26-case labels unchanged.',
    'causal_event':'obs204 choseDOWN4 scheduled221; overlap visible225; lives decrement351. Post-contact answers are not treated as causes.',
    'ground_truth_sent_to_model':False},indent=2)+'\n')
print(json.dumps({'tasks':len(tasks),'paid_api_calls':0}))
