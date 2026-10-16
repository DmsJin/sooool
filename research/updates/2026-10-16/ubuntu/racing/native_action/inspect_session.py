"""Local-only wire check. No requests reach a model; no headers or image bytes logged."""
import base64,hashlib,json,pathlib,sys,threading,argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import run
from session_native import SessionNative
p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('images',type=pathlib.Path,nargs=2);a=p.parse_args();a.out.mkdir(exist_ok=False,parents=True);captured=[]
class H(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  b=b'{"data":[]}';self.send_response(200);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));images=[];user_text=[]
  for m in body.get('input',[]):
   if m.get('role')!='user':continue
   for c in m.get('content',[]):
    if c.get('type')=='input_image':
     url=c.get('image_url','');images.append({'sha256':hashlib.sha256(base64.b64decode(url.split(',',1)[1])).hexdigest() if url.startswith('data:') else 'not-inline','detail':c.get('detail')})
    elif c.get('type')=='input_text':user_text.append(c.get('text','')[:100])
  captured.append({'images':images,'user_text':user_text,'prompt_cache_key':body.get('prompt_cache_key')})
  ident=str(len(captured));text='[[0,0,1]]';msg={'type':'message','id':'msg_mock_'+ident,'role':'assistant','status':'completed','content':[{'type':'output_text','text':text,'annotations':[]}]};response={'id':'resp_mock_'+ident,'object':'response','model':'gpt-6.1-sol','created_at':1,'status':'completed','output':[msg],'usage':{'input_tokens':10,'output_tokens':10,'total_tokens':20,'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}}}
  events=[{'type':'response.created','response':{**response,'status':'in_progress','output':[]}}, {'type':'response.output_item.added','output_index':0,'item':{**msg,'status':'in_progress','content':[]}}, {'type':'response.content_part.added','item_id':msg['id'],'output_index':0,'content_index':0,'part':{'type':'output_text','text':'','annotations':[]}}, {'type':'response.output_text.delta','item_id':msg['id'],'output_index':0,'content_index':0,'delta':text}, {'type':'response.output_text.done','item_id':msg['id'],'output_index':0,'content_index':0,'text':text}, {'type':'response.output_item.done','output_index':0,'item':msg}, {'type':'response.completed','response':response}]
  b=(''.join('data: '+json.dumps(e)+'\n\n' for e in events)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
server=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=server.serve_forever,daemon=True).start();original=run.subprocess.Popen

def launch(cmd,*args,**kwargs):
 cmd=list(cmd);cmd[1:1]=['-c','model_providers.research_subscription.base_url='+json.dumps(f'http://127.0.0.1:{server.server_port}/v1')];return original(cmd,*args,**kwargs)
run.subprocess.Popen=launch;client=None
try:
 client=SessionNative(a.out/'worker')
 for i,f in enumerate(a.images):
  try:client.act('Return only [[0,0,1]].',[f.read_bytes()],a.out/f'call_{i}')
  except RuntimeError:pass
 expected=[hashlib.sha256(f.read_bytes()).hexdigest() for f in a.images];result={'expected_image_hashes':expected,'captured':captured,'paid_calls':0,'model_calls':0,'LOCAL_MOCK_TRANSPORT_ONLY':True,'history_preserved_exact_images':len(captured)==2 and [[x['sha256'] for x in c['images']] for c in captured]==[expected[:1],expected],'stable_cache_key':len(captured)==2 and captured[0]['prompt_cache_key']==captured[1]['prompt_cache_key']};run.write(a.out/'image_wire_check.json',result);print(json.dumps(result),flush=True)
finally:
 if client:client.close()
 run.subprocess.Popen=original;server.shutdown();server.server_close()
