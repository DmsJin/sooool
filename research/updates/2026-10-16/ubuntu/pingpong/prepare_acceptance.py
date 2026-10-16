"""Prepare a frozen ten-seed subscription acceptance plan. Does not run models."""
import argparse,json,shutil
from pathlib import Path
from freeze import capture,digest

def prepare(a):
    source=a.source;summary=json.loads((source/'summary.json').read_text());protocol=json.loads((source/'protocol.json').read_text());replay=json.loads((source/'verified_replay.json').read_text())
    if not summary['finished'] or summary['winner']!='A' or summary.get('failure'):raise ValueError('Freeze a completed, selected development winner')
    if not replay.get('native_digest_exact_match') or replay.get('camera_pngs_verified')!=summary['calls'] or replay.get('digest')!=summary['digest']:
        raise ValueError('Require independent exact replay of all decision images and final digest')
    if summary['level']!=1 or summary['slowdown']!=10:raise ValueError('This acceptance plan targets native default L1/S10')
    if '_executor_' not in summary['variant']:raise ValueError('First complete an execution-delay development trial')
    scripts=Path(__file__).parent
    current={p.name:digest(p) for p in scripts.glob('*.py')}
    if current!=protocol['source_hashes']:raise ValueError('Development winner used different code; revalidate the selected policy before freezing')
    if digest(a.profile)!=protocol['profile_sha256']:raise ValueError('Profile differs from selected development condition')
    experiment=json.loads((scripts/'protocol.json').read_text());acceptance=experiment['acceptance_proposal'];seeds=acceptance['held_out_seeds']
    if len(seeds)!=10 or len(set(seeds))!=10:raise ValueError('Expected ten distinct reserved seeds')
    a.output.mkdir(parents=True,exist_ok=False);profile=a.output/'profile.json';shutil.copy2(a.profile,profile)
    manifest=capture(scripts,profile,scripts.resolve().parents[1],[a.model_config,*a.external])
    manifest.update(selected_source=str(source),selected_digest=summary['digest'],variant=summary['variant'],model=protocol['model'],level=1,slowdown=10,held_out_seeds=seeds,delay_scale=protocol['delay_scale'])
    path=a.output/'freeze.json';path.write_text(json.dumps(manifest,indent=2))
    round_plan_path=source.parents[1]/'plan.json'
    round_plan=json.loads(round_plan_path.read_text()) if round_plan_path.exists() else {}
    gap=float(round_plan.get('gap_s',6))
    if not 0<=gap<=60:raise ValueError('Source subscription admission gap is invalid')
    plan={'profile':str(profile),'freeze_manifest':str(path),'parallel_episodes':2,'gap_s':gap,'delay_scale':protocol['delay_scale'],
          'jobs':[{'name':f'heldout-seed{seed}','seed':seed,'variant':summary['variant']} for seed in seeds],
          'target_wins':acceptance['target_wins_out_of_ten'],'independent_confirmation_required':True,
          'paid_api_calls':0,'scope':'Frozen ten-seed subscription acceptance under sampled API delay and execution blockage. Native image replay and later real API transfer remain required.'}
    (a.output/'plan.json').write_text(json.dumps(plan,indent=2));print(json.dumps({'prepared_seeds':seeds,'model_calls':0,'paid_api_calls':0,'plan':str(a.output/'plan.json')}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--external',type=Path,nargs='*',default=[]);p.add_argument('--model-config',type=Path,default=Path('/home/ubuntu/lzj/coding-agent-suite/outputs/suite-20ep/sol-parallel-20261011T211538Z/configs/asterix_sol.yaml'));prepare(p.parse_args())
