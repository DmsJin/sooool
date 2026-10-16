"""Native-only outer-prompt A/B transport; no paid API fallback."""
import asyncio,itertools,json
from .model_subscription import CheckedNativeProvider
class OuterProvider(CheckedNativeProvider):
 serial=itertools.count()
 def __init__(self,variant):
  super().__init__()
  if variant not in ('baseline','minimal'):raise ValueError('Unknown outer variant')
  self.variant=variant
 async def start(self):
  socket=['/tmp/dfjk-research-ssh.sock','/tmp/dfjk-research-ssh-1.sock','/tmp/dfjk-research-ssh-3.sock'][next(self.serial)%3]
  command='/home/ubuntu/lzj/envs/coding-agent-suite/bin/python -u /tmp/dfjk-model-timing/experiments/rhythm/subscription_outer_worker.py --variant '+self.variant+' --system-text-file /tmp/dfjk-model-timing/experiments/rhythm/outer/minimal-system.txt --service-tier priority'
  self.process=await asyncio.create_subprocess_exec('ssh','-S',socket,'-o','BatchMode=yes','-o','ConnectTimeout=8','ubuntu@35.223.106.107',command,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
  line=await asyncio.wait_for(self.process.stdout.readline(),90)
  if not line:
   await self.close();raise RuntimeError('Outer worker exited before ready')
  ready=json.loads(line)
  if not ready.get('ready') or ready.get('auth')!='chatgpt' or ready.get('variant')!=self.variant:
   await self.close();raise RuntimeError('Outer worker did not confirm requested subscription configuration: '+str(ready)[:500])
  self.configuration=ready
  return self

def factory(variant):return OuterProvider(variant)
