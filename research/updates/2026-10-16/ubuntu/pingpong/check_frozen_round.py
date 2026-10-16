"""Round accounting integration check with an explicit fake worker; no model."""
import json,shutil,subprocess,sys,tempfile
from pathlib import Path
from freeze import capture

def main():
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp);scripts=root/'scripts';scripts.mkdir()
  for name in ('freeze.py','run_round.py'):shutil.copy2(Path(__file__).with_name(name),scripts/name)
  (scripts/'policy_marker.py').write_text('VERSION=1\n')
  (scripts/'simulate.py').write_text('''import argparse,hashlib,json\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--profile',type=Path);p.add_argument('--seed',type=int);a,extra=p.parse_known_args();a.output.mkdir()\nsource={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in Path(__file__).parent.glob('*.py')}\n(a.output/'protocol.json').write_text(json.dumps({'source_hashes':source,'profile_sha256':hashlib.sha256(a.profile.read_bytes()).hexdigest()}))\n(a.output/'summary.json').write_text(json.dumps({'finished':True,'winner':'A'}))\nif (a.profile.parent/'mutate').exists() and a.seed==2:Path(__file__).with_name('policy_marker.py').write_text('VERSION=2\\n')\n''')
  profile=root/'profile.json';profile.write_text('{}')
  manifest=root/'freeze.json';manifest.write_text(json.dumps(capture(scripts,profile)))
  plan=root/'plan.json';plan.write_text(json.dumps({'profile':str(profile),'freeze_manifest':str(manifest),'parallel_episodes':1,'jobs':[{'name':'seed2','seed':2,'variant':'fixture'},{'name':'seed5','seed':5,'variant':'fixture'}]}))
  def run(out):
   subprocess.run([sys.executable,str(scripts/'run_round.py'),'--plan',str(plan),'--output',str(out),'--python',sys.executable],check=True,capture_output=True,text=True)
   return json.loads((out/'results.json').read_text())
  good=run(root/'good');assert good['completed']==2 and good['wins']==2
  (root/'mutate').touch();bad=run(root/'bad')
  assert bad['completed']==0 and all(row['status']=='incomplete' for row in bad['jobs'].values())
  assert not (root/'bad/seed5/active_process.json').exists(),'Changed policy was launched for the second seed'
  print(json.dumps({'scope':'fake-worker accounting check, not game performance','model_calls':0,'unchanged_frozen_jobs_verified':2,'changed_policy_jobs_excluded':2,'next_changed_job_not_dispatched':True}))
if __name__=='__main__':main()
