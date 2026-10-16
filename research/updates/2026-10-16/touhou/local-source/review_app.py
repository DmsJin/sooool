"""Local human annotation UI for frozen visual devsets; no model/game calls."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit

STATUSES = {'unreviewed', 'pass', 'issue', 'uncertain'}
ISSUES = {'grounding','prediction','duration','tracking','danger','stopping','transition','resources','input','rubric','other'}


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, dataset: Path, output: Path):
        self.dataset = dataset.resolve()
        self.output = output
        self.lock = threading.Lock()
        manifest = json.loads((dataset/'manifest.json').read_text())
        self.cases = []
        for case in manifest['examples']:
            card = json.loads((dataset/case['private_labels']).read_text())
            self.cases.append({**card, 'source':case['source'], 'images':case['images']})
        self.ids = {case['id'] for case in self.cases}
        if len(self.ids) != len(self.cases):
            raise ValueError('Duplicate case IDs')
        self.data = json.loads(output.read_text()) if output.exists() else {'version':1, 'dataset':str(self.dataset), 'annotations':{}}
        if self.data['dataset'] != str(self.dataset):
            raise ValueError('Annotation file belongs to a different dataset')

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.data))

    def update(self, request):
        ident = request.get('id')
        if ident not in self.ids:
            raise ValueError('Unknown case')
        patch = request.get('annotation', {})
        if set(patch) != {'status','issues','notes','expected'}:
            raise ValueError('Invalid annotation fields')
        if patch['status'] not in STATUSES:
            raise ValueError('Invalid status')
        if not isinstance(patch['issues'], list) or any(not isinstance(x,str) or x not in ISSUES for x in patch['issues']):
            raise ValueError('Invalid issue types')
        if any(not isinstance(patch[k],str) or len(patch[k])>20000 for k in ['notes','expected']):
            raise ValueError('Invalid text')
        with self.lock:
            previous = self.data['annotations'].get(ident, {'revision':0})
            if type(request.get('revision')) is not int or request['revision'] != previous['revision']:
                raise Conflict('This case changed in another tab. Refresh before editing.')
            item = {**patch, 'issues':sorted(set(patch['issues'])), 'revision':previous['revision']+1,
                    'updated_at':datetime.now(timezone.utc).isoformat()}
            updated = {**self.data, 'annotations':{**self.data['annotations'],ident:item}}
            self.output.parent.mkdir(parents=True,exist_ok=True)
            temporary = self.output.with_suffix('.tmp')
            temporary.write_text(json.dumps(updated,ensure_ascii=False,indent=2))
            temporary.replace(self.output)
            self.data = updated
            return item


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, value, content_type='application/json; charset=utf-8'):
            body = value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/':
                self.reply(200,Path(__file__).with_name('review_app.html').read_bytes(),'text/html; charset=utf-8')
            elif path == '/api/dataset':
                self.reply(200,{'cases':store.cases,'output':str(store.output)})
            elif path == '/api/annotations':
                self.reply(200,store.snapshot())
            elif path.startswith('/assets/cases/'):
                target = (store.dataset/path[len('/assets/'):]).resolve()
                if not target.is_relative_to(store.dataset/'cases') or target.suffix != '.png' or not target.is_file():
                    self.reply(404,{'error':'Image not found'})
                else:
                    self.reply(200,target.read_bytes(),'image/png')
            else:
                self.reply(404,{'error':'Not found'})

        def do_POST(self):
            if urlsplit(self.path).path != '/api/annotations':
                self.reply(404,{'error':'Not found'});return
            if self.headers.get('Origin') not in (None,'http://'+self.headers.get('Host','')):
                self.reply(403,{'error':'Invalid origin'});return
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 200000:
                    raise ValueError('Invalid body length')
                result = store.update(json.loads(self.rfile.read(length)))
                self.reply(200,result)
            except Conflict as exc:
                self.reply(409,{'error':str(exc)})
            except (ValueError,TypeError,KeyError) as exc:
                self.reply(400,{'error':str(exc)})
            except OSError:
                self.reply(500,{'error':'Could not save to disk; your browser draft is retained.'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--port',type=int,default=8797)
    args = parser.parse_args()
    store = Store(args.dataset,args.output)
    print(f'Annotation UI: http://localhost:{args.port}/\nSaved annotations: {args.output}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),handler(store)).serve_forever()


if __name__ == '__main__':
    main()
