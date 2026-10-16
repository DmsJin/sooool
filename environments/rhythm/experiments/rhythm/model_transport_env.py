"""Generic receipt cursors reduce transport volume; actions remain literal."""
from .model_env import ModelVisualEnv
class TransportVisualEnv(ModelVisualEnv):
 async def public_clock_ms(self):
  return await self._page.evaluate('performance.now()')
 async def snapshot(self,after_seq=0):
  return await self._page.evaluate('cursor=>window.__modelExecutor.snapshot(cursor)',after_seq)
 async def apply(self,plan):
  return await self._page.evaluate('''plan=>{
   const e=window.__modelExecutor, before=e.snapshot().cursor;
   const result=e.submit(plan);
   result.rawacks=result.rawacks.filter(ack=>ack.seq>before);
   return result;
  }''',plan)
