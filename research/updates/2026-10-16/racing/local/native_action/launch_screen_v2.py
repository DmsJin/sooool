import pathlib,json,subprocess,os,sys
root=pathlib.Path(__file__).resolve().parents[1];out=root/'results/native-screen-v2';out.mkdir(exist_ok=False)
cases=[('calibrated','front',3,3,'issue',3),('calibrated','chase',3,3,'issue',3),('predict','chase',3,3,'issue',3),('commit','chase',3,3,'issue',3),('calibrated','front',3,1,'arrival',2),('calibrated','chase',3,1,'arrival',2)]
manifest=[]
for variant,camera,images,chunk,anchor,profile in cases:
 ident=f'{variant}-{camera}-h{images}-c{chunk}-{anchor}';folder=out/ident;log=(out/(ident+'.log')).open('w');cmd=[sys.executable,str(root/'native_action/simulate.py'),'--out',str(folder),'--profile',str(root/f'results/native-profile-v1/condition_{profile}.json'),'--variant',variant,'--camera',camera,'--history',str(images),'--chunk',str(chunk),'--anchor',anchor,'--screen-seconds','12','--workers','4','--cadence','.3']
 proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close();manifest.append({'id':ident,'pid':proc.pid,'configuration':cmd})
(out/'manifest.json').write_text(json.dumps({'screen_only_not_full_match':True,'episodes_parallel':6,'real_subscription_workers_per_episode':4,'max_native_workers':24,'cases':manifest},indent=2));print(json.dumps(manifest),flush=True)
