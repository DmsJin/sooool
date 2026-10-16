"""Run a frozen matrix of full matches; never turn incomplete episodes into losses."""
import argparse,concurrent.futures as cf,json,os,pathlib,subprocess,sys,time

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=pathlib.Path);p.add_argument('--profile',required=True,type=pathlib.Path)
 p.add_argument('--matrix',required=True,type=pathlib.Path);p.add_argument('--parallel',type=int,default=8)
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);matrix=json.loads(a.matrix.read_text());results=[]
 (a.out/'matrix.json').write_text(json.dumps(matrix,indent=2))
 def run(row):
  tag=row['id'];out=a.out/tag;cmd=[sys.executable,str(pathlib.Path(__file__).with_name('run.py')),'sim','--out',str(out),'--profile',str(a.profile)]
  for k,v in row.items():
   if k!='id':cmd.extend(['--'+k,str(v)])
  with (a.out/(tag+'.log')).open('w') as log:
   pr=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   (a.out/(tag+'.pid')).write_text(str(pr.pid));code=pr.wait()
  summary=json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else {'status':'incomplete'}
  return {'id':tag,'returncode':code,'condition':row,**summary}
 with cf.ThreadPoolExecutor(max_workers=a.parallel) as pool:
  futures=[pool.submit(run,row) for row in matrix]
  for f in cf.as_completed(futures):
   results.append(f.result());status={'finished':len(results),'total':len(matrix),'episodes':results}
   tmp=a.out/'status.tmp';tmp.write_text(json.dumps(status,indent=2));tmp.replace(a.out/'status.json')
   print(json.dumps(results[-1]),flush=True)
 groups={}
 for row in matrix:
  key=(row.get('variant','basic'),row.get('slowdown',1),row.get('history',1),row.get('chunk',1),row.get('anchor','arrival'),row.get('control','servo'),row.get('cadence',.2),row.get('capacity',8))
  groups.setdefault(key,[]).append(row['id'])
 byid={r['id']:r for r in results};report=[]
 for key,ids in groups.items():
  group=[byid[i] for i in ids];complete=all(r['status']=='complete' and r.get('replay_matches') for r in group)
  report.append({'condition':key,'n':len(ids),'complete':complete,'wins':sum(r.get('won',False) for r in group) if complete else None})
 (a.out/'groups.json').write_text(json.dumps(report,indent=2));print('GROUPS '+json.dumps(report),flush=True)

if __name__=='__main__':main()
