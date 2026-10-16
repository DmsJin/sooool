"""Free reference-driver check of the genuine wall-clock HTTP service, not a GPT result."""
import argparse,json,os,pathlib,signal,socket,subprocess,sys,time
import requests
from run import ROOT,write

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=pathlib.Path);a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 env=dict(os.environ);env.update(MUJOCO_GL='egl',LP_NUM_THREADS='1',RCB_DATA=str(a.out),RO_PLUGIN=str(ROOT/'sports/racing/plugin.py'),RO_SPORT='racing',RO_FORMAT='match',RO_SEATS='A',RO_SEED='101',RO_LEVEL='1',RO_FIRST='A',RO_SLOWDOWN='1',RCB_ACTION_LEVEL='low',RCB_PLAY='program',RCB_ACT_RULE='program',RCB_PLAYER_MODE='oracle',RCB_PORT=str(port),RCB_RENDER_VIDEO='0',RCB_BROADCAST='0')
 log=(a.out/'server.log').open('w');pr=subprocess.Popen([sys.executable,'-m','core.serve'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 http=requests.Session();base=f'http://127.0.0.1:{port}/A'
 def call(ep,body=None):
  r=http.get(base+'/'+ep,timeout=30) if body is None else http.post(base+'/'+ep,json=body,timeout=30)
  if r.status_code==409 and ep=='observe' and r.json().get('now',{}).get('done'):return r.json()
  if r.status_code!=200:raise RuntimeError(f'{ep}: HTTP {r.status_code}')
  return r.json()
 try:
  for _ in range(120):
   if pr.poll() is not None:raise RuntimeError('service exited')
   try:spec=call('spec');break
   except requests.RequestException:time.sleep(.25)
  else:raise RuntimeError('service startup timeout')
  sys.path.insert(0,str(ROOT/'sports/racing'));from builtin_players import Reference
  ref=Reference(spec,'A',101);call('start',{});started=time.monotonic()
  while True:
   v=call('observe',{});s=v['now']
   if s.get('done'):break
   if s.get('awaiting_review') or s.get('phase')=='review':call('ready',{'why':'Free reference preflight heat completed.','plan':'Continue reference driver.'});continue
   cmd=ref.act({'state':s,'observation':v['observation']})
   if cmd is not None:
    try:call('act',cmd)
    except RuntimeError:
     if call('status').get('phase') in ['review','over']:continue
     raise
   time.sleep(.15)
  os.kill(pr.pid,signal.SIGUSR1)
  for _ in range(240):
   final=json.loads((a.out/'final.json').read_text())
   if final.get('graded_ready'):break
   time.sleep(.25)
  else:raise RuntimeError('collect timeout')
  summary={'driver':'reference, NOT GPT','api_cost_usd':0,'winner':final.get('match_winner'),'deterministic':final.get('deterministic'),'valid_trial':final.get('valid_trial'),'sim_lag':final.get('sim_lag'),'wall_seconds':time.monotonic()-started}
  write(a.out/'summary.json',summary);print(json.dumps(summary),flush=True)
 finally:
  if pr.poll() is None:
   os.killpg(pr.pid,signal.SIGTERM)
   try:pr.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(pr.pid,signal.SIGKILL);pr.wait()
  log.close()

if __name__=='__main__':main()
