"""Subscription transport with strict correlation; no gameplay decisions."""
import asyncio,base64,json,uuid
from .providers import NativeProvider
class CheckedNativeProvider(NativeProvider):
 async def act(self,prompt,images):
  async with self.lock:
   if self.process is None or self.process.returncode is not None:
    await self.start()
   rid=uuid.uuid4().hex
   row={'id':rid,'prompt':prompt,'images':[base64.b64encode(x).decode() for x in images]}
   try:
    self.process.stdin.write((json.dumps(row)+'\n').encode());await self.process.stdin.drain()
    line=await asyncio.wait_for(self.process.stdout.readline(),150)
    if not line:raise RuntimeError('Subscription worker exited')
    result=json.loads(line)
    if result.get('id')!=rid:raise RuntimeError('Subscription response correlation mismatch')
    if result.get('error'):raise RuntimeError(result['error'])
    return result['answer'],result['meta']
   except BaseException:
    await self.close()
    raise
