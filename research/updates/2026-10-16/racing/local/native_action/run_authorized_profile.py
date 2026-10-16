"""Pass the credential explicitly supplied in this thread to SSH stdin, memory only."""
import pathlib,json,re,pexpect,sys
thread=pathlib.Path('/home/zihan/.codex/sessions/2026/10/15/rollout-2026-10-15T09-43-45-01a13e84-6151-70f1-bec1-fc05fea1f2fa.jsonl');key=None
with thread.open() as f:
 for line in f:
  o=json.loads(line);p=o.get('payload',{})
  if (o.get('type')=='event_msg' and p.get('type')=='user_message') or (o.get('type')=='response_item' and p.get('role')=='user'):
   match=re.search(r'sk-proj-[A-Za-z0-9_-]{80,}',json.dumps(p))
   if match:key=match.group();break
if key is None:raise SystemExit('Existing user-provided credential not found')
cmd='RACING_ENV_ROOT=/home/ubuntu/wzh/racing-autoresearch-20261015 RACING_FORECAST_PROFILE_OUT=/home/ubuntu/wzh/robot-racing-research/results/native-forecast-profile-v2 PYTHONDONTWRITEBYTECODE=1 /home/ubuntu/wzh/racing-autoresearch-20261015/venv/bin/python /home/ubuntu/wzh/robot-racing-research/native_action/profile_forecast.py'
child=pexpect.spawn('ssh',['-tt','-S','/tmp/racing-research-ssh','ubuntu@35.223.106.107',cmd],encoding='utf-8',timeout=60);child.setecho(False)
try:
 child.expect_exact('API credential for serial forecast profiling (memory only): ');child.sendline(key)
 while True:
  index=child.expect([pexpect.EOF,pexpect.TIMEOUT],timeout=50)
  if index==0:break
  print('Serial API profile is still running.',flush=True)
 print(child.before.replace(key,'[redacted]'),flush=True);child.close();code=child.exitstatus if child.exitstatus is not None else 1;key=None;raise SystemExit(code)
except (pexpect.ExceptionPexpect,OSError) as e:
 print(type(e).__name__,flush=True);print(child.before.replace(key,'[redacted]'),flush=True);key=None;raise SystemExit(1)
