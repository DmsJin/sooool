import pathlib,json,subprocess,os,sys
root=pathlib.Path(__file__).resolve().parents[1];out=root/'results/native-curriculum-v1';out.mkdir(exist_ok=False)
cases=[(v,c,seed) for seed in [101,111] for v,c in [('predict','front'),('geometry','front'),('commit','front'),('calibrated','front'),('gentle','front'),('predict','chase'),('geometry','chase'),('commit','chase'),('calibrated','chase'),('gentle','chase')]]
manifest=[]
for variant,camera,seed in cases:
 images,chunk,anchor,profile=3,1,'arrival',2
 ident=f'5x-{variant}-{camera}-s{seed}';folder=out/ident;log=(out/(ident+'.log')).open('w');cmd=[sys.executable,str(root/'native_action/simulate.py'),'--out',str(folder),'--profile',str(root/f'results/native-profile-auto-v2/condition_{profile}.json'),'--variant',variant,'--camera',camera,'--history',str(images),'--chunk',str(chunk),'--anchor',anchor,'--screen-seconds','12','--slowdown','5','--seed',str(seed),'--workers','1','--cadence','.3']
 proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close();manifest.append({'id':ident,'pid':proc.pid,'configuration':cmd})
(out/'manifest.json').write_text(json.dumps({'screen_only_not_full_match':True,'episodes_parallel':20,'real_subscription_workers_per_episode':1,'max_native_workers':20,'image_wire_verified':True,'localImage_detail':'auto','cases':manifest},indent=2));print(json.dumps(manifest),flush=True)
