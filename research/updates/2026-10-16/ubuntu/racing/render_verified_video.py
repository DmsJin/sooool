"""Read-only replay rendering of the existing real API win; no model calls."""
import os,sys,pathlib,json,bisect,hashlib,time
os.environ.setdefault('MUJOCO_GL','egl');os.environ.setdefault('LP_NUM_THREADS','1')
env=pathlib.Path(os.environ['RACING_ENV_ROOT']);sys.path.insert(0,str(env))
from core.episode import read_rows,header_cfg,load_plugin,replay
from core import spec as specmod
from core.spectator import video_camera
from renderers import load,CameraDef
from PIL import Image,ImageDraw,ImageFont
source=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
plugin=str(env/'sports/racing/plugin.py');sport=load_plugin(plugin);rows=read_rows(source/'service/episode.jsonl');cfg=header_cfg(next(r for r in rows if r['ev']=='header'));decl=specmod.load(plugin)
model=sport.build(cfg);camera=video_camera(sport,cfg,model,decl);camera.update(width=320,height=213);overview=CameraDef.from_dict(camera)
renderer=load('mujoco')(sport.scene(cfg));fontpath='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
def font(size):
 try:return ImageFont.truetype(fontpath,size)
 except OSError:return ImageFont.load_default()
f24,f18,f14=font(24),font(18),font(14)
actions=[json.loads(l) for l in (source/'waypoint_actions.jsonl').read_text().splitlines()];times=[a['game_time'] for a in actions]
goals={int(p.parent.name.split('_')[1]):json.loads(json.loads(p.read_text())['answer'])[0] for p in source.glob('decision_*/result.json')}
count=0;last=None;started=time.monotonic()
def draw(m):
 global count,last
 if m.k%10 and m.phase().state!='finished':return
 chase=m.cameras('A',{'camera':'chase'})[0];chase.update(width=640,height=426)
 front=m.cameras('A',None)[0]
 images=renderer.render(m.render_state(),[CameraDef.from_dict(chase),overview,CameraDef.from_dict(front)])
 canvas=Image.new('RGB',(960,640),(15,23,42));d=ImageDraw.Draw(canvas)
 canvas.paste(Image.fromarray(images[0]),(0,70));canvas.paste(Image.fromarray(images[1]),(640,70));canvas.paste(Image.fromarray(images[2]).resize((320,213)),(640,283))
 state=m.observe('A');race=state['race'];own=state['own'];heat=state['heat'];score=race['heats_won'];t=m.k*m.dt
 d.text((18,10),'ROBOT RACING  |  REAL API  |  1x  |  LEVEL 1',font=f24,fill='white')
 d.text((18,43),'Verified seed 304 replay - same recorded actions; no new model inference',font=f14,fill=(148,163,184))
 for box,label in [((10,80),'CHASE CAMERA'),((650,80),'OVERVIEW'),((650,293),'MODEL FRONT VIEW')]:
  x,y=box;d.rectangle((x-4,y-3,x+195,y+22),fill=(15,23,42));d.text((x,y),label,font=f14,fill='white')
 d.text((20,510),f'HEAT {heat}     BLUE / GPT  {score.get("A",0)} : {score.get("opponent",0)}  ORANGE / OPPONENT',font=f24,fill=(96,165,250))
 d.text((20,548),f'Game time {t:05.1f}s   |   Actual speed {own["forward_speed"]:.2f} m/s',font=f18,fill='white')
 i=bisect.bisect_right(times,t)-1
 if i>=0:
  seq=actions[i]['model_seq'];g=goals.get(seq)
  if g:d.text((20,579),f'GPT goal #{seq}: speed {g[0]:.1f} m/s  |  lane offset {g[1]:+.2f} m  |  lookahead {g[2]:.1f} m',font=f18,fill=(203,213,225))
 d.text((20,614),'1x game-time replay; frozen review waits omitted. GPT goals + 5 Hz visual executor.',font=f14,fill=(148,163,184))
 canvas.save(out/f'frame_{count:05d}.png');last=canvas;count+=1
 if count%100==0:print(json.dumps({'frames':count,'game_s':round(t,1),'render_wall_s':round(time.monotonic()-started,1)}),flush=True)
try:result=replay(sport,rows,observer=draw,decl=decl)
finally:renderer.close()
original=json.loads((source/'service/replay_check.json').read_text());assert result['state_sha']==original['state_sha'];assert result['winner']=='A'
# Hold the verified final result for two seconds for readability.
for _ in range(20):last.save(out/f'frame_{count:05d}.png');count+=1
(out/'render_audit.json').write_text(json.dumps({'source':'existing actual API seed304','speed':1,'fps':10,'frames':count,'state_sha':result['state_sha'],'matches_original_replay':True,'winner':'A','model_calls_for_render':0},indent=2))
print('RENDER_COMPLETE '+str(count),flush=True)
