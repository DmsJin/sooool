"""One causal GPT conversation per episode. Caller MUST allow one pending request."""
import sys,pathlib,threading,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from run import Native,write
class SessionNative(Native):
 def __init__(self,*args,**kwargs):
  self.retained=None;self.turn_count=0;self.act_lock=threading.Lock();super().__init__(*args,**kwargs)
 def rpc(self,method,params):
  if method=='thread/start':
   if self.retained is None:self.retained=super().rpc(method,params)
   return self.retained
  if method=='thread/unsubscribe' and self.retained and params['threadId']==self.retained['thread']['id']:return {}
  return super().rpc(method,params)
 def act(self,*args,**kwargs):
  if not self.act_lock.acquire(blocking=False):raise RuntimeError('overlapping session decisions forbidden')
  try:
   answer,meta=super().act(*args,**kwargs);self.turn_count+=1;meta.update(session_mode=True,session_turn=self.turn_count,session_thread_sha256=hashlib.sha256(self.retained['thread']['id'].encode()).hexdigest());directory=kwargs.get('directory',args[2] if len(args)>2 else None);write(pathlib.Path(directory)/'result.json',{'answer':answer,**meta});return answer,meta
  finally:self.act_lock.release()
