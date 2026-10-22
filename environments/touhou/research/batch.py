"""Bounded multi-episode subscription evaluation; never invokes paid API."""
import argparse,concurrent.futures as cf,json,pathlib,subprocess,sys,time,threading,shutil
from .run_episode import write


def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--episode-workers',type=int,default=8)
 a=p.parse_args();a.config=a.config.resolve();a.output=a.output.resolve();spec=json.loads(a.config.read_text());a.output.mkdir(parents=True,exist_ok=False)
 jobs=spec['jobs'];results=[];lock=threading.Lock()
 source=a.output/'frozen_source';source.mkdir();shutil.copytree(pathlib.Path(__file__).parent,source/'research',ignore=shutil.ignore_patterns('__pycache__'))
 write(a.output/'protocol.json',spec)
 def one(job):
  name=job['name'];config={**spec['base'],**job['config']}
  if config['provider']!='subscription' or config['mode']!='sim':raise ValueError('Batch is subscription simulation only')
  configpath=a.output/(name+'.config.json');write(configpath,config)
  out=a.output/name;logpath=a.output/(name+'.log')
  with logpath.open('w') as log:
   proc=subprocess.Popen([sys.executable,'-u','-m','research.run_episode','--config',str(configpath),'--output',str(out)],stdout=log,stderr=subprocess.STDOUT,cwd=str(source))
   write(a.output/(name+'.process.json'),{'pid':proc.pid,'started':time.time()})
   code=proc.wait()
  summarypath=out/'summary.json'
  result=json.loads(summarypath.read_text()) if summarypath.exists() else {'name':name,'error':'incomplete','exit':code,'failure':str(out/'failure.json')}
  result['name']=name
  with lock:
   results.append(result);write(a.output/'status.json',{'status':'running','completed':len(results),'total':len(jobs),'episodes':results,'api_spend_usd':0})
  print(json.dumps(result),flush=True);return result
 with cf.ThreadPoolExecutor(max_workers=a.episode_workers) as pool:list(pool.map(one,jobs))
 write(a.output/'status.json',{'status':'complete','episodes':results,'api_spend_usd':0})

if __name__=='__main__':main()
