"""Causal subscription training using the user-selected minimal Codex outer."""
import argparse,asyncio,hashlib,json,uuid
from pathlib import Path
from .model_training import run_episode
from .model_outer_provider import OuterProvider
ROOT=Path(__file__).resolve().parents[2]

async def run(args):
 args.outer='minimal'
 tag='minimal-outer-'+uuid.uuid4().hex[:8]
 provenance=Path(args.run_root)/tag
 provenance.mkdir(parents=True,exist_ok=False)
 files=['experiments/rhythm/model_minimal_training.py','experiments/rhythm/model_outer_provider.py','experiments/rhythm/subscription_outer_worker.py','experiments/rhythm/outer/minimal-system.txt']
 (provenance/'sources.json').write_text(json.dumps({'outer':'minimal','paid_api_calls':0,'task_prompt_modified':False,'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in files}},indent=2))
 class Provider(OuterProvider):
  def __init__(self):super().__init__('minimal')
  async def start(self):
   await super().start()
   with(provenance/'workers.jsonl').open('a')as f:f.write(json.dumps(self.configuration)+'\n')
   return self
 result=await run_episode(args,provider_factory=Provider)
 (provenance/'result-reference.json').write_text(json.dumps({'episode_output':result['output'],'outer':'minimal'}))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--profile');p.add_argument('--joint-profile');p.add_argument('--candidate',default='minimal-model-v11');p.add_argument('--seed',type=int,default=43)
 p.add_argument('--actors',type=int,default=16);p.add_argument('--cadence',type=float,default=.12);p.add_argument('--frames',type=int,default=1)
 p.add_argument('--ack-limit',type=int,default=8);p.add_argument('--compact',action='store_true');p.add_argument('--lean',action='store_true')
 p.add_argument('--hide-rtt',action='store_true',help='Omit live RTT history from the actor input; joint lean mode only')
 p.add_argument('--memory',required=True);p.add_argument('--clock-offset-ms',type=float,default=10000);p.add_argument('--max-requests',type=int,default=400)
 p.add_argument('--duration',type=float,default=30.001);p.add_argument('--chart');p.add_argument('--browser-executable')
 p.add_argument('--url',default='http://127.0.0.1:18896');p.add_argument('--run-root',default=str(ROOT/'experiments/rhythm/runs/model-timing'))
 asyncio.run(run(p.parse_args()))
