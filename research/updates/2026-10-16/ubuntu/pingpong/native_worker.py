"""One subscription-only native client, isolated from simulator files."""
import base64
import json
from pathlib import Path
import sys
import signal

from subscription import SubscriptionClient

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    managed='--managed-tail' in sys.argv
    startup=None;client=None
    if managed:
        from worker_lifecycle import ManagedStartup
        startup=ManagedStartup(out/'managed_process.json')
        def stop(signum,frame):startup.stop()
        signal.signal(signal.SIGTERM,stop)
    try:
        if managed:
            client=SubscriptionClient.__new__(SubscriptionClient)
            with startup:
                client.__init__(Path('/home/ubuntu/lzj/coding-agent-suite'),out,quota_stop_percent=99,compact_instructions=True,lean_context=True)
            print(json.dumps({'ready':True,'pid':__import__('os').getpid()}),flush=True)
        else:
            client=SubscriptionClient(Path('/home/ubuntu/lzj/coding-agent-suite'),out,quota_stop_percent=99,compact_instructions=True,lean_context=True)
        for line in sys.stdin:
            req=json.loads(line)
            answer,meta=client.act(req['prompt'],[base64.b64decode(req['image_b64'])],Path(req['directory']))
            print(json.dumps({'answer':answer,**meta}),flush=True)
    finally:
        if managed:signal.signal(signal.SIGTERM,signal.SIG_IGN)
        try:
            if client is not None and hasattr(client,'runner'):client.close()
        finally:
            if startup is not None:startup.cleanup()

if __name__=='__main__':main()
