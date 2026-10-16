import sys,json,pathlib,tempfile,contextlib
sys.path.insert(0,'/home/ubuntu/lzj/coding-agent-suite/code')
from latency_bench.core.config import load_config
from latency_bench.policy.base import PolicyRunner
from latency_bench.core.types import PolicyOutput
import latency_bench.policy.codex as codex
from latency_bench.eval.driver import run_from_config
root=pathlib.Path(sys.argv[1])
all_records=[json.load(open(p)) for p in sorted((root/'agent/episode_000').glob('decision_*/call.json'))]
records=[r for r in all_records if r['status']=='completed']
final='--save-final' in sys.argv
class Replay(PolicyRunner):
    def __init__(self,resolver):self.resolver=resolver;self.index=0
    def predict_batch(self,observations):return [self.predict(obs) for obs in observations]
    def predict(self,obs):
        r=records[self.index];self.index+=1
        assert r['env_step']==obs.env_step,(r['env_step'],obs.env_step)
        return PolicyOutput(action=self.resolver.resolve(r['action']))
codex.build_codex_policy=lambda cfg,resolver:Replay(resolver)
config=load_config(root/'resolved_config.yaml')
config['evaluation']['eval_max_steps']=all_records[-1]['env_step'] if final and all_records[-1]['status']!='completed' else records[-1]['env_step']+1
config['logging']['video']['enabled']=final
config['logging']['video']['num_bins']=1
manager=contextlib.nullcontext(str(root/'final_replay')) if final else tempfile.TemporaryDirectory(prefix='asterix-replay-',dir='/home/ubuntu/wzh/expts-sol/runtime/tmp')
with manager as tmp:
    config['logging']['output_dir']=tmp
    metrics=run_from_config(config,episode_ids=[0])
    out=dict(recorded_decisions=len(records),frames=metrics[0].survival_steps,score=metrics[0].episode_return,
             note='Deterministic replay of recorded actions with original simulator; zero model calls.')
    (root/'progress_replay.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
