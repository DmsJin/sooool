from pathlib import Path
import json,os
b=Path('/home/ubuntu/wzh/touhou-sol-study/optimization-v9-confirm-20261016')
print('screen_completed',len(list((b/'confirmation').glob('call_*/comparison.json'))))
for pid in (3339645,3340286):
 try:os.kill(pid,0);print('pid_alive',pid)
 except ProcessLookupError:print('pid_done',pid)
for f in sorted((b/'closed-loop-four').glob('*.process.json')):
 d=json.loads(f.read_text());ep=f.parent/f.name.replace('.process.json','');a=ep/'actions.jsonl';rows=[json.loads(l) for l in a.read_text().splitlines()] if a.exists() else []
 try:os.kill(d['pid'],0);alive=True
 except ProcessLookupError:alive=False
 s=json.loads((ep/'summary.json').read_text()) if (ep/'summary.json').exists() else {}
 print(json.dumps({'name':ep.name,'pid':d['pid'],'alive':alive,'applied':len(rows),'last_logic':rows[-1].get('logical_frame') if rows else 0,'summary':{k:s.get(k) for k in ('status','game_s','calls','hits','boss_hp','bombs')}}))
for n in ('confirmation.log','closed-loop-four.log'):
 text=(b/n).read_text() if (b/n).exists() else ''
 if 'Traceback' in text:print('ERROR_LOG',n,text[-1200:])
