"""Inspect outbound request SHAPE on localhost; no model output or paid API.

Never logs headers, credential values, raw messages or image data. A local 400
terminates the turn after recording field lengths, tool names and image detail.
"""
import argparse,hashlib,json,pathlib,threading,ctypes,ctypes.util,gzip
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import run


def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--lean',action='store_true');p.add_argument('--empty-tools',action='store_true');p.add_argument('--ultrafast-mode',action='store_true');p.add_argument('--builtin-provider',action='store_true');p.add_argument('--openai-name',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
 captured=[]
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   raw=b'{"data":[]}'
   self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
  def do_POST(self):
   raw=self.rfile.read(int(self.headers['Content-Length']));encoding=self.headers.get('Content-Encoding','')
   if encoding=='zstd':
    z=ctypes.CDLL(ctypes.util.find_library('zstd') or '/usr/lib/x86_64-linux-gnu/libzstd.so.1');z.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t];z.ZSTD_decompress.restype=ctypes.c_size_t;z.ZSTD_isError.argtypes=[ctypes.c_size_t];z.ZSTD_isError.restype=ctypes.c_uint;dest=ctypes.create_string_buffer(16*1024*1024);src=ctypes.create_string_buffer(raw);n=z.ZSTD_decompress(dest,len(dest),src,len(raw))
    if z.ZSTD_isError(n):raise RuntimeError('local zstd inspection failed')
    raw=dest.raw[:n]
   elif encoding=='gzip':raw=gzip.decompress(raw)
   body=json.loads(raw)
   def shapes(x):
    if isinstance(x,list):return [shapes(v) for v in x]
    if isinstance(x,dict):
     return {k:(len(v) if k in ['text','image_url'] and isinstance(v,str) else shapes(v)) for k,v in x.items() if k in ['type','role','content','text','image_url','detail']}
    return x
   instructions=body.get('instructions','')
   inputs=body.get('input',[])
   text_blocks=[c.get('text','') for m in inputs if m.get('role')=='developer' for c in m.get('content',[]) if c.get('type')=='input_text']
   additional=[m for m in inputs if m.get('type')=='additional_tools']
   def names(x):
    if isinstance(x,list):return [n for v in x for n in names(v)]
    if isinstance(x,dict):return ([x['name']] if isinstance(x.get('name'),str) else [])+[n for v in x.values() for n in names(v)]
    return []
   row={'path':self.path,'content_encoding':encoding,'body_keys':list(body),'contains_ultrafast': 'ultrafast' in json.dumps(body),'model':body.get('model'),'service_tier':body.get('service_tier'),'tier_headers':{k:v for k,v in self.headers.items() if k.lower().endswith('tier')},'instructions_chars':len(instructions),'instructions_match_minimal':instructions.strip()==run.MINIMAL_SYSTEM.strip(),'developer_blocks':[{'chars':len(t),'matches_minimal':t.strip()==run.MINIMAL_SYSTEM.strip(),'preview':t[:120]} for t in text_blocks],'additional_tools_chars':sum(len(json.dumps(m)) for m in additional),'additional_tool_names':names(additional),'tools':[{'type':t.get('type'),'name':t.get('name') or t.get('function',{}).get('name'),'json_chars':len(json.dumps(t))} for t in body.get('tools',[])],'input_shape':shapes(inputs),'reasoning':body.get('reasoning'),'paid_calls':0,'local_shape_only':True}
   captured.append(row);run.write(a.out/'request_shape.json',row)
   raw=b'{"error":{"message":"Local request inspection finished","type":"request_inspection"}}'
   self.send_response(400);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 original=run.subprocess.Popen
 def launch(cmd,*args,**kwargs):
  cmd=list(cmd)
  if a.openai_name:cmd=[x.replace('model_providers.research_subscription.name="Subscription SSE"','model_providers.research_subscription.name="OpenAI"') for x in cmd]
  provider='openai' if a.builtin_provider else 'research_subscription'
  if a.builtin_provider:
   cmd=[x.replace('model_provider="research_subscription"','model_provider="openai"') for x in cmd]
   cmd[1:1]=['-c','model_providers.openai.supports_websockets=false']
  cmd[1:1]=['-c',f'model_providers.{provider}.base_url='+json.dumps(f'http://127.0.0.1:{server.server_port}/v1')]
  if a.lean:cmd[1:1]=['--disable','code_mode_host','--disable','code_mode','--disable','multi_agent_v2','--disable','unified_exec']
  if a.ultrafast_mode:cmd[1:1]=['--enable','ultrafast_mode']
  return original(cmd,*args,**kwargs)
 run.subprocess.Popen=launch;client=None
 try:
  client=run.Native(a.out/'worker')
  original_rpc=client.rpc
  def rpc(method,params):
   if a.empty_tools and method=='thread/start':params={**params,'dynamicTools':[],'environments':[],'selectedCapabilityRoots':[],'serviceTier':'ultrafast'}
   if a.empty_tools and method=='turn/start':params={**params,'serviceTierForTurn':'ultrafast'}
   return original_rpc(method,params)
  client.rpc=rpc
  try:client.act('Return only [[0,0,0.1]].',[],a.out/'call')
  except RuntimeError:pass # Expected local HTTP400, not a model evaluation.
  if not captured:raise RuntimeError('No localhost request captured')
  print(json.dumps(captured[-1]),flush=True)
 finally:
  if client:client.close()
  run.subprocess.Popen=original;server.shutdown();server.server_close()

if __name__=='__main__':main()
