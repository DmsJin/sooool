"""Materialize indexed evidence from the optional branch of this same repository."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]

def materialize(entry,destination,fetch=False):
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Existing artifact checksum mismatch')
        return destination
    refs=[entry['git_ref'],'refs/remotes/origin/'+entry['git_ref']]
    if fetch:
        subprocess.run(['git','fetch','--depth=1','origin',entry['git_ref']+':refs/remotes/origin/'+entry['git_ref']],cwd=ROOT,check=True)
    if entry.get('parts'):
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_name(destination.name+'.incoming')
        with temporary.open('wb')as output:
            for part in entry['parts']:
                item={**part,'git_ref':entry['git_ref']}
                local=materialize(item,ROOT/part['git_path'])
                with local.open('rb')as source:
                    import shutil
                    shutil.copyfileobj(source,output)
        if hashlib.sha256(temporary.read_bytes()).hexdigest()!=entry['sha256']:
            temporary.unlink();raise ValueError('Assembled archive checksum mismatch')
        temporary.replace(destination)
        return destination
    payload=None
    for ref in refs:
        r=subprocess.run(['git','show',ref+':'+entry['git_path']],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if r.returncode==0:payload=r.stdout;break
    if payload is None:raise RuntimeError('Evidence branch is not available locally. Rerun with --fetch after configuring origin.')
    if hashlib.sha256(payload).hexdigest()!=entry['sha256']:raise ValueError('Evidence branch checksum mismatch')
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(payload)
    return destination

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('--fetch',action='store_true');a=p.parse_args()
    entries=[json.loads(x)for x in(ROOT/'artifacts/index.jsonl').read_text().splitlines()]
    entries += [json.loads(x)for x in(ROOT/'research/discussions/index.jsonl').read_text().splitlines()]
    entry=next((x for x in entries if a.path in (x['path'],x['git_path'])),None)
    if entry is None:raise ValueError('Path must be indexed in artifacts or discussions')
    print(materialize(entry,ROOT/entry['git_path'],a.fetch))
