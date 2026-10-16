"""One subscription-only native client, isolated from simulator files."""
import base64
import json
from pathlib import Path
import sys

from subscription import SubscriptionClient

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    client=SubscriptionClient(Path('/home/ubuntu/lzj/coding-agent-suite'),out,quota_stop_percent=99,compact_instructions=True,lean_context=True)
    try:
        for line in sys.stdin:
            req=json.loads(line)
            answer,meta=client.act(req['prompt'],[base64.b64decode(req['image_b64'])],Path(req['directory']))
            print(json.dumps({'answer':answer,**meta}),flush=True)
    finally:client.close()

if __name__=='__main__':main()
