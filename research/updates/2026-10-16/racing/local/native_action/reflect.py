"""Subscription-only prompt revision from recorded legal frames and GPT actions."""
import pathlib,sys,json,concurrent.futures as cf
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from run import Native,write
root=pathlib.Path(__file__).resolve().parents[1];out=root/'results/native-reflect-v1';out.mkdir(exist_ok=False)
cases=[('single-calibrated',root/'results/native-single-v1/calibrated-chase-s111'),('single-gentle',root/'results/native-single-v1/gentle-chase-s101'),('forecast-geometry',root/'results/native-forecast-v1/geometry-chase-s121'),('forecast-commit',root/'results/native-forecast-v1/commit-chase-s131')]
def work(case):
 name,src=case;d=out/name;d.mkdir();decisions=sorted(src.glob('decision_*/input.json'));images=[];records=[]
 for f in decisions:
  ans=f.with_name('result.json')
  if not ans.exists():continue
  inp=json.loads(f.read_text());result=json.loads(ans.read_text());obs=json.loads(inp['prompt'].split('Visible observations:',1)[1]);im=sorted(f.parent.glob('image_*.png'))[-1];images.append(im.read_bytes());records.append({'legal_observation':obs[-1],'GPT_action':result['answer'],'image_number':len(images)})
 task='''You are revising a native realtime visual racing GPT policy after a failed attempt. Images are the exact original legal chase frames, chronological. Each attached image corresponds to the numbered record. Inspect them yourself. There is NO CV, lane follower, pure pursuit, waypoint extraction or code driving policy. A blind executor delivers only GPT speed/steering/duration commands unchanged, newest plan replaces old, expiry brakes. You may revise the MODEL TASK PROMPT ONLY, never write code. The model will still receive current raw images and own/referee telemetry. Opponent1.75m/s, positive steering LEFT, speed[-1.5,4], steering[-.48,.48], command duration[.05,3]. Camera rotates with car: chase240x160,70deg vertical FOV,pitch35.4deg down,height1.505m,1.5m behind; blue car is us. Wheelbase.46m. Model actions arrive about1.6 game seconds after observation at1x; the held previous command continues meanwhile. At5x this delay is about.32 game seconds. A stopped car stays stopped until arrival. Aim to complete a clean lap and win, not park or exploit referee disqualifications. Diagnose the observed failure: what do raw pictures say about road direction, car heading, steering magnitude and timing, held controls, braking and recovery? Then write an improved concise reusable policy paragraph that could be added to the driver's task prompt, independent of this seed and time. Do not prescribe a fixed timed route or actions based on hidden world state. A few physical intuitions are fine, but no executable code or external tool use. Return ONLY a JSON object with exactly string fields diagnosis and policy. Policy at most350 words. Never call tools.\nRecorded legal observations and ACTUAL earlier GPT outputs:\n'''+json.dumps(records,separators=(',',':'))
 write(d/'source.json',{'source':str(src),'records':records,'task':task})
 client=Native(d/'worker')
 try:
  answer,meta=client.act(task,images,d/'response');obj=json.loads(answer);assert set(obj)=={'diagnosis','policy'} and all(isinstance(v,str) and v for v in obj.values());assert len(obj['policy'].split())<=350;write(d/'revision.json',obj);return name
 finally:client.close()
with cf.ThreadPoolExecutor(max_workers=4) as pool:
 for name in pool.map(work,cases):print(name,flush=True)
