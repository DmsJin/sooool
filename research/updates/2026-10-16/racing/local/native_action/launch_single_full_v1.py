import pathlib,json,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1];out=root/'results/native-single-full-v1';out.mkdir(exist_ok=False);profile=root/'results/native-single-profile-v1/condition.json';p=json.loads(profile.read_text());assert p['valid_outputs']==p['n']==6
manifest=[]
for seed in [101,111,121,131]:
 for variant in ['predict','geometry','commit','gentle','calibrated']:
  ident=f'{variant}-chase-s{seed}';log=(out/(ident+'.log')).open('w');cmd=[sys.executable,str(root/'native_action/simulate.py'),'--out',str(out/ident),'--profile',str(profile),'--variant',variant,'--camera','chase','--history','3','--chunk','1','--anchor','arrival','--session','--max-duration','3','--capacity','1','--workers','1','--screen-seconds','0','--cadence','.3','--seed',str(seed)];proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close();manifest.append({'id':ident,'pid':proc.pid,'configuration':cmd})
(out/'manifest.json').write_text(json.dumps({'screen_only_not_full_match':False,'episodes_parallel':20,'max_native_workers':20,'one_pending_plan_per_episode':True,'model_chosen_validity_max_seconds':3,'code_driving_policy':False,'cases':manifest},indent=2));print(json.dumps({'episodes_launched':len(manifest),'pids':[m['pid'] for m in manifest]}),flush=True)
