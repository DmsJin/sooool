"""Verify checked-in archive hashes and unpack under a chosen local directory."""
import argparse
import json
from pathlib import Path
import tarfile
import shutil
from fetch_artifacts import materialize
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('--output',type=Path,default=ROOT/'runs/historical');a=p.parse_args()
entries=[json.loads(x)for x in(ROOT/'artifacts/index.jsonl').read_text().splitlines()]
entry=next((x for x in entries if x['path']==a.archive),None)
if entry is None:raise ValueError('Archive must be listed in artifacts/index.jsonl')
source=materialize(entry,ROOT/'artifacts'/entry['path'])
a.output.mkdir(parents=True,exist_ok=True);target=a.output.resolve()
with tarfile.open(source)as tar:
 for item in tar.getmembers():
  dest=(target/item.name).resolve()
  if not dest.is_relative_to(target)or not (item.isfile()or item.isdir()or item.islnk()):raise ValueError('Unsafe archive member')
  if item.islnk():
   link=(target/item.linkname).resolve()
   if not link.is_relative_to(target):raise ValueError('Unsafe internal hardlink')
 for item in tar.getmembers():
  dest=target/item.name
  if item.isdir():dest.mkdir(parents=True,exist_ok=True);continue
  dest.parent.mkdir(parents=True,exist_ok=True)
  with tar.extractfile(item)as source,dest.open('wb')as output:shutil.copyfileobj(source,output)
print(target)
