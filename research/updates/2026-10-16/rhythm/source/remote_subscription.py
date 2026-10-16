"""Native subscription RPC worker; no API credentials or fallback."""
import base64, contextlib, json, pathlib, sys, tempfile, traceback
sys.path.insert(0,'/home/ubuntu/wzh/expts-sol/scripts/iterative-intercept-20261014')
from subscription_client import SubscriptionClient
out=pathlib.Path(tempfile.mkdtemp(prefix='dfjk-native-'))
with contextlib.redirect_stdout(sys.stderr):
    client=SubscriptionClient(pathlib.Path('/home/ubuntu/lzj/coding-agent-suite'),out)
print(json.dumps({'ready':True,'auth':'chatgpt','model':client.runner.settings['model']}),flush=True)
try:
    for line in sys.stdin:
        row=json.loads(line)
        if row.get('op')=='close':break
        if row.get('op')=='ping':
            print(json.dumps({'id':row['id'],'ok':True,'auth':'chatgpt'}),flush=True);continue
        try:
            with contextlib.redirect_stdout(sys.stderr):
                answer,meta=client.act(row['prompt'],[base64.b64decode(x) for x in row['images']],out/('request_'+str(client.count)))
            print(json.dumps({'id':row['id'],'answer':answer,'meta':meta}),flush=True)
        except Exception as e:
            print(json.dumps({'id':row['id'],'error':type(e).__name__+': '+str(e)[:300]}),flush=True)
finally:
    client.close()
