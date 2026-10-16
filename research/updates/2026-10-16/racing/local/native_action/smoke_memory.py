"""Subscription-only schema/vision checks on saved raw images. Not gameplay/profile."""
import sys,pathlib,json,concurrent.futures as cf
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from run import Native,write
import recurrent
root=pathlib.Path(__file__).resolve().parents[1];out=root/'results/native-memory-smoke-v1';out.mkdir(exist_ok=False,parents=True);source=root/'results/native-screen-v4/geometry-chase-h3-c1-arrival';applied=[json.loads(x) for x in (source/'applied.jsonl').read_text().splitlines()]
def one(index):
 folder=source/f'decision_{index:05d}';d=json.loads((folder/'input.json').read_text());states=json.loads(d['prompt'].split('Visible observations:',1)[1]);images=[x.read_bytes() for x in sorted(folder.glob('image_*.png'))];history=[{'t':r['step']*.01,'command':r['command']} for r in applied if r['step']<=states[-1]['step']][-16:]
 task=recurrent.prompt(states,'geometry',1,'arrival',{'p50':2.28,'mean':2.28,'p95':2.28},camera='chase',past_commands=history);client=Native(out/f'worker_{index}')
 try:
  write(out/f'call_{index}'/'input.json',{'prompt':task,'schema_smoke_only':True});answer,meta=client.act(task,images,out/f'call_{index}');commands,memory,scene=recurrent.parse(answer,1,'arrival');r={'index':index,'commands':commands,'memory':memory,'scene':scene,**meta};write(out/f'call_{index}'/'parsed.json',r);return r
 finally:client.close()
with cf.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,[0,20,40,55]))
write(out/'summary.json',{'schema_smoke_not_gameplay':True,'paid_api_calls':0,'results':results});print(json.dumps([{'index':r['index'],'commands':r['commands'],'scene':r['scene'],'memory':r['memory']} for r in results]),flush=True)
