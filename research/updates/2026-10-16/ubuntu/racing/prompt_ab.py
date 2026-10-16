"""Randomly interleaved subscription-only outer-prompt comparison.

Identical frozen task text and RGB inputs within each pair. Existing racing
controller versus the user's minimal system + isolated context. No API calls.
Short branches assess local driving quality, not match win rate or accuracy.
"""
import argparse,hashlib,json,pathlib,random,statistics,sys,time,subprocess,concurrent.futures as cf
from run import Native,ROOT,parse,write,append,make_world,observe


def summarize(rows):
 groups={}
 for condition in ['current','minimal']:
  rs=[r for r in rows if r['condition']==condition]
  good=[r for r in rs if r['valid']]
  times=sorted(r['total_wall_seconds'] for r in rs)
  if not times:
   groups[condition]={'n':0};continue
  def mean_token(k):
   vals=[(r.get('token_usage') or {}).get('last',{}).get(k) for r in good]
   vals=[x for x in vals if x is not None]
   return statistics.mean(vals) if vals else None
  groups[condition]={'n':len(rs),'valid':len(good),'mean_seconds':statistics.mean(times),'median_seconds':statistics.median(times),'p95_seconds':times[min(len(times)-1,int(.95*len(times)))],'mean_input_tokens':mean_token('inputTokens'),'mean_cached_input_tokens':mean_token('cachedInputTokens'),'mean_output_tokens':mean_token('outputTokens'),'mean_reasoning_tokens':mean_token('reasoningOutputTokens')}
 pairs={}
 for r in rows:pairs.setdefault(r['pair'],{})[r['condition']]=r
 complete=[v for v in pairs.values() if len(v)==2]
 reductions=[p['current']['total_wall_seconds']-p['minimal']['total_wall_seconds'] for p in complete]
 rng=random.Random(8173)
 boot=sorted(statistics.mean(rng.choices(reductions,k=len(reductions))) for _ in range(4000)) if reductions else []
 return {'groups':groups,'paired_n':len(complete),'minimal_faster_pairs':sum(x>0 for x in reductions),'mean_paired_seconds_saved':statistics.mean(reductions) if reductions else None,'paired_bootstrap_95ci_seconds_saved':[boot[100],boot[3899]] if boot else None,'mean_latency_reduction_fraction':1-groups['minimal']['mean_seconds']/groups['current']['mean_seconds'] if all(groups[c]['n'] for c in groups) else None,'api_cost_usd':0,'limitation':'Output validity is not decision accuracy. Local one-second counterfactuals are not complete-match win rate.'}


def benchmark(a):
 a.out.mkdir(parents=True,exist_ok=False);rng=random.Random(20261015)
 samples=[]
 for seed in [101,111,121]:
  episode=ROOT/f'results/round4/metric-closed-5x-s{seed}'
  issued=[json.loads(s) for s in (episode/'issued.jsonl').read_text().splitlines()]
  for j in range(a.pairs//3):
   # Stratify across both heats rather than choosing only easy straight frames.
   lo=int((j+.15)*len(issued)/(a.pairs//3));hi=int((j+.85)*len(issued)/(a.pairs//3))
   row=issued[rng.randrange(lo,max(lo+1,hi))]
   samples.append({'episode':str(episode),'seed':seed,**row})
 rng.shuffle(samples)
 orders=[['current','minimal'],['minimal','current']]*(len(samples)//2)
 rng.shuffle(orders)
 for i,s in enumerate(samples):s.update(pair=i,order=orders[i])
 write(a.out/'manifest.json',{'model':'gpt-6.1-sol','effort':'low','tier':'ultrafast','random_seed':20261015,'pairs':samples,'paid_calls':0,'comparison':'Existing short racing baseInstructions and global context vs requested system.txt plus isolated reduced context. Task prompt, observations, actions, model, effort and tier unchanged.','unsupported_cli_flags':['--ignore-user-config'],'unsupported_legacy_config':['tools.view_image; use features.view_image=false']})
 clients={};rows=[];started=time.monotonic()
 try:
  for c in ['current','minimal']:
   t=time.perf_counter();clients[c]=Native(a.out/f'worker_{c}',outer=c)
   append(a.out/'startup.jsonl',{'condition':c,'seconds':time.perf_counter()-t})
  # Warm both connections outside reported measurements.
  warm=samples[0];d=pathlib.Path(warm['episode'])/f'decision_{warm["seq"]:05d}'
  text=json.loads((d/'input.json').read_text())['prompt'];images=[p.read_bytes() for p in sorted(d.glob('image_*.png'))]
  for c in rng.sample(['current','minimal'],2):clients[c].act(text,images,a.out/f'warmup_{c}')
  for s in samples:
   d=pathlib.Path(s['episode'])/f'decision_{s["seq"]:05d}'
   inp=json.loads((d/'input.json').read_text());text=inp['prompt'];images=[p.read_bytes() for p in sorted(d.glob('image_*.png'))]
   hashes=[hashlib.sha256(x).hexdigest() for x in images]
   if hashes!=s['image_sha256']:raise RuntimeError('Frozen observation hash mismatch')
   for c in s['order']:
    target=a.out/f'pair_{s["pair"]:03d}'/c
    write(target/'input.json',{'prompt':text,'prompt_sha256':hashlib.sha256(text.encode()).hexdigest(),'image_sha256':hashes})
    t=time.perf_counter();row={'pair':s['pair'],'condition':c,'valid':False,'seq':s['seq'],'seed':s['seed']}
    try:
     answer,meta=clients[c].act(text,images,target);row.update(meta,answer=answer)
     row['commands']=parse(answer,1);row['valid']=True
    except Exception as e:row['error']=type(e).__name__+': '+str(e)
    row['total_wall_seconds']=time.perf_counter()-t;rows.append(row);append(a.out/'measurements.jsonl',row)
    write(a.out/'summary.json',summarize(rows))
   print('AB_PROGRESS '+json.dumps({'completed_pairs':s['pair']+1,'total':len(samples),'elapsed_seconds':time.monotonic()-started,'summary':summarize(rows)['groups']}),flush=True)
 finally:
  for client in clients.values():client.close()
 write(a.out/'summary.json',summarize(rows));print('AB_DONE '+json.dumps(summarize(rows)),flush=True)


def branch(a):
 """Evaluator-only simulator progress never enters a model request."""
 from core.episode import read_rows
 s=json.loads((a.out/'manifest.json').read_text())['pairs'][a.pair]
 episode=pathlib.Path(s['episode']);cfg=json.loads((episode/'config.json').read_text())
 trial=next(json.loads(x) for x in (a.out/'measurements.jsonl').read_text().splitlines() if json.loads(x)['pair']==a.pair and json.loads(x)['condition']==a.condition)
 if not trial['valid']:return
 sport,_,m,views,_=make_world(cfg['seed'],cfg['level'],cfg['slowdown'])
 rows=[r for r in read_rows(episode/'episode.jsonl') if r['ev'] in ['cmd','resume']]
 ix=0
 def original_until(step):
  nonlocal ix
  while m.k<step:
   while ix<len(rows) and rows[ix]['k']==m.k:
    r=rows[ix]
    if r['ev']=='resume':m.resume()
    else:m.apply(r['seat'],r['cmd'])
    ix+=1
   m.step()
 original_until(s['seen_step']);_,image=observe(m,views)
 if hashlib.sha256(image).hexdigest()!=s['image_sha256'][-1]:raise RuntimeError('Counterfactual prefix observation differs')
 original_until(s['due_step']);r=m.r
 start={'progress':r.progress['A'],'warnings':r.warnings['A'],'walls':r.wall_steps['A'],'obstacles':r.obstacle_steps['A'],'heat':r.heat}
 speed,steer,_=trial['commands'][0];m.apply('A',{'type':'drive','speed':speed,'steering':steer})
 steps=0
 while steps<100 and not r.awaiting_review and not r.done:m.step();steps+=1
 result={'pair':a.pair,'condition':a.condition,'seed':s['seed'],'observation_hash_verified':True,'held_command_game_seconds':steps*m.dt,'progress_delta_m':r.progress['A']-start['progress'],'warnings_delta':r.warnings['A']-start['warnings'],'wall_contact_steps':r.wall_steps['A']-start['walls'],'obstacle_contact_steps':r.obstacle_steps['A']-start['obstacles'],'limitation':'One-second hold from identical replayed state and identical sampled API arrival. No later model interventions; not a match win-rate measurement.'}
 write(a.out/f'pair_{a.pair:03d}'/a.condition/'branch.json',result);print(json.dumps(result),flush=True)


def quality(a):
 measurements=[json.loads(x) for x in (a.out/'measurements.jsonl').read_text().splitlines()]
 def evaluate(row):
  cmd=[sys.executable,__file__,'branch','--out',str(a.out),'--pair',str(row['pair']),'--condition',row['condition']]
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
  if r.returncode:raise RuntimeError(r.stderr[-1000:])
  return json.loads((a.out/f'pair_{row["pair"]:03d}'/row['condition']/'branch.json').read_text())
 with cf.ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(evaluate,[r for r in measurements if r['valid']]))
 groups={}
 for c in ['current','minimal']:
  rs=[r for r in rows if r['condition']==c]
  groups[c]={'n':len(rs),'mean_progress_delta_m':statistics.mean(r['progress_delta_m'] for r in rs),'branches_with_wall_contact':sum(r['wall_contact_steps']>0 for r in rs),'total_wall_contact_steps':sum(r['wall_contact_steps'] for r in rs),'branches_with_obstacle_contact':sum(r['obstacle_contact_steps']>0 for r in rs),'total_obstacle_contact_steps':sum(r['obstacle_contact_steps'] for r in rs),'warnings_delta':sum(r['warnings_delta'] for r in rs)}
 result={'groups':groups,'all_observation_hashes_verified':all(r['observation_hash_verified'] for r in rows),'limitation':'Same-state one-game-second branches using original sampled API delay for both conditions. Tests local action quality only, not complete episodes or real API performance. Simulator progress used only by evaluator, never supplied to model.'}
 write(a.out/'quality_summary.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['benchmark','branch','quality']);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--pairs',type=int,default=24);p.add_argument('--pair',type=int);p.add_argument('--condition',choices=['current','minimal']);a=p.parse_args()
 if a.mode=='benchmark':benchmark(a)
 elif a.mode=='quality':quality(a)
 else:branch(a)
