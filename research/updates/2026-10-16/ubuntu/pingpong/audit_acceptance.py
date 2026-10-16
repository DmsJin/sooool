"""Audit one frozen subscription acceptance round, never mark the goal complete."""
import argparse,json
from pathlib import Path
from freeze import verify

def audit(root):
 plan=json.loads((root/'plan.json').read_text());manifest=json.loads((root/'freeze_manifest.json').read_text());report=json.loads((root/'results.json').read_text());errors=[];checked=[];wins=0
 try:verify(manifest,Path(__file__).parent,plan['profile'])
 except (ValueError,OSError) as exc:errors.append(str(exc))
 jobs=plan['jobs'];seeds=[job['seed'] for job in jobs]
 if len(jobs)!=10 or len(set(seeds))!=10 or seeds!=manifest['held_out_seeds']:errors.append('Expected the ten frozen reserved seeds')
 if set(report['jobs'])!={j['name'] for j in jobs}:errors.append('Some planned jobs are missing or extra')
 for job in jobs:
  try:
   row=report['jobs'][job['name']];assert row['status']=='complete','Episode incomplete'
   source=Path(row['output']);summary=json.loads((source/'summary.json').read_text());protocol=json.loads((source/'protocol.json').read_text());replay=json.loads((source/'verified_replay.json').read_text())
   assert summary['finished'] and not summary.get('failure'),'Episode not a completed game'
   assert summary['seed']==job['seed'] and summary['variant']==manifest['variant'],'Seed or policy mismatch'
   assert summary['level']==manifest['level'] and summary['slowdown']==manifest['slowdown'],'Task condition mismatch'
   assert protocol['source_hashes']==manifest['source_hashes'] and protocol['profile_sha256']==manifest['profile_sha256'],'Frozen source/profile mismatch'
   assert protocol['model']==manifest['model'] and protocol['delay_scale']==manifest['delay_scale'],'Model or delay mismatch'
   assert replay['fresh_native_process'] and replay['native_digest_exact_match'],'Missing fresh native replay'
   assert replay['digest']==summary['digest'] and replay['scores']==summary['scores'] and replay['final_step']==summary['k'],'Replay final state mismatch'
   assert replay['camera_pngs_verified']==summary['calls'] and replay['observations_verified']==summary['calls'],'Not every decision camera/state verified'
   wins+=summary['winner']=='A';checked.append(job['name'])
  except (KeyError,ValueError,OSError,AssertionError) as exc:errors.append(job['name']+': '+str(exc))
 result={'scope':'Frozen subscription acceptance only; independent confirmation and real API transfer remain required','verified_jobs':len(checked),'wins':wins,'required_jobs':10,'target_wins':plan['target_wins'],'stage_passed':not errors and len(checked)==10 and wins>=plan['target_wins'],'goal_complete':False,'errors':errors}
 (root/'acceptance_audit.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('round',type=Path);print(json.dumps(audit(p.parse_args().round)),flush=True)
