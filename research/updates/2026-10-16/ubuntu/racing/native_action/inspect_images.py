"""Local-only wire check. No requests reach a model; no headers or image bytes logged."""
import base64,hashlib,json,pathlib,sys,threading,argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import run
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
  captured.append({'images':images,'user_text':user_text});b=b'{"error":{"message":"local-only image check complete","type":"request_inspection"}}';self.send_response(400);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
server=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=server.serve_forever,daemon=True).start();original=run.subprocess.Popen

def launch(cmd,*args,**kwargs):
 cmd=list(cmd);cmd[1:1]=['-c','model_providers.research_subscription.base_url='+json.dumps(f'http://127.0.0.1:{server.server_port}/v1')];return original(cmd,*args,**kwargs)
run.subprocess.Popen=launch;client=None
try:
 client=run.Native(a.out/'worker')
 for i,f in enumerate(a.images):
  try:client.act('Return only [[0,0,1]].',[f.read_bytes()],a.out/f'call_{i}')
  except RuntimeError:pass
 expected=[hashlib.sha256(f.read_bytes()).hexdigest() for f in a.images];result={'expected_image_hashes':expected,'captured':captured,'paid_calls':0,'model_calls':0,'inline_images_present':len(captured)==2 and all(len(c['images'])==1 for c in captured)};run.write(a.out/'image_wire_check.json',result);print(json.dumps(result),flush=True)
finally:
 if client:client.close()
 run.subprocess.Popen=original;server.shutdown();server.server_close()
