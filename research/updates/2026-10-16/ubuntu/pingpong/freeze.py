"""Hash-only experiment freeze. Credentials and home directories are excluded."""
import argparse,hashlib,json
from pathlib import Path

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def capture(scripts,profile,environment=None,external=()):
    scripts=Path(scripts)
    result={'source_hashes':{p.name:digest(p) for p in sorted(scripts.glob('*.py'))},
            'profile_sha256':digest(profile),'external_hashes':{str(Path(p)):digest(p) for p in external}}
    if environment is not None:
        root=Path(environment);paths=[]
        for folder in ('core','sports/tabletennis','renderers'):
            paths.extend(p for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts)
        result['environment_root']=str(root)
        result['environment_hashes']={str(p.relative_to(root)):digest(p) for p in sorted(paths)}
    return result

def verify(manifest,scripts,profile):
    current=capture(scripts,profile,manifest.get('environment_root'),manifest.get('external_hashes',{}))
    for key in ('source_hashes','profile_sha256','external_hashes','environment_hashes'):
        if current.get(key)!=manifest.get(key):raise ValueError('Frozen experiment changed: '+key)
    return True

def main():
    p=argparse.ArgumentParser();p.add_argument('--scripts',type=Path,default=Path(__file__).parent);p.add_argument('--profile',type=Path,required=True);p.add_argument('--environment',type=Path);p.add_argument('--external',type=Path,nargs='*',default=[]);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Never overwrite a frozen manifest')
    manifest=capture(a.scripts,a.profile,a.environment,a.external)
    a.output.write_text(json.dumps(manifest,indent=2));print(json.dumps({'manifest':str(a.output),'source_files':len(manifest['source_hashes']),'environment_files':len(manifest.get('environment_hashes',{})),'paid_calls':0}))
if __name__=='__main__':main()
