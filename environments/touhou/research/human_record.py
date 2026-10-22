"""Local human demonstration recorder; no model calls or gameplay changes.

Serve: python -m research.human_record --port 8796 --output /path/to/demos
Verify: python -m research.human_record --verify /path/to/demos/run --url http://127.0.0.1:8796/game/
Extract: python -m research.human_record --extract /path/to/demos/run --frame 1200
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import shutil
import threading
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
ENGINE_HASH = '348e81340d4a09f8b488193daf0b4e395afa2755d34f249585ff5e1ffe787aa4'


def write(path, value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2));temporary.replace(path)


def persist_event_batch(folder, data):
    """Ordered immutable batches make retries idempotent, including lost acks."""
    directory=folder/'event_batches';directory.mkdir(exist_ok=True)
    seq=data['batch_seq'];assert type(seq) is int and seq>=0
    payload={key:data[key] for key in ['batch_seq','keys','actions']}
    batches=sorted(directory.glob('batch-*.json'));assert seq<=len(batches),'Out of order event batch'
    path=directory/f'batch-{seq:06d}.json'
    if path.exists():assert json.loads(path.read_text())==payload,'Retry changed event batch'
    else:write(path,payload)
    batches=[json.loads(path.read_text()) for path in sorted(directory.glob('batch-*.json'))]
    for field,name in [('keys','key_edges.jsonl'),('actions','actions.jsonl')]:
        target=folder/name;temporary=target.with_suffix('.tmp')
        temporary.write_text(''.join(json.dumps(row)+'\n' for batch in batches for row in batch[field]));temporary.replace(target)


def persist_frame_batch(folder, items):
    assert isinstance(items,list) and 1<=len(items)<=8
    directory=folder/'frames'
    for item in items:
        png=base64.b64decode(item['png'].split(',',1)[1]);assert png.startswith(b'\x89PNG\r\n\x1a\n')
        digest=hashlib.sha256(png).hexdigest();stamp=round(item['clock']['wall_ms']*1000)
        stem=f"visual-{item['clock']['visual_frame']:06d}-{stamp:012d}-{digest[:12]}"
        image=directory/(stem+'.png');metadata=directory/(stem+'.json')
        if not image.exists():image.write_bytes(png)
        row={'frame':item['frame'],'held':item['held'],'clock':item['clock'],'png':'frames/'+image.name,'sha256':digest}
        if metadata.exists():assert json.loads(metadata.read_text())==row,'Retry changed frame metadata'
        else:write(metadata,row)
    records=[json.loads(path.read_text()) for path in directory.glob('visual-*.json')]
    records.sort(key=lambda row:(row['clock']['visual_frame'],row['clock']['wall_ms']))
    target=folder/'frames.jsonl';temporary=target.with_suffix('.tmp')
    temporary.write_text(''.join(json.dumps(row)+'\n' for row in records));temporary.replace(target)


def verify(directory, url):
    from .environment import BrowserEnv
    from .state_compare import compare_engine_state
    manifest = json.loads((directory/'manifest.json').read_text())
    expected = json.loads((directory/'final_state.json').read_text())
    actions = [json.loads(s) for s in (directory/'actions.jsonl').read_text().splitlines()]
    with BrowserEnv(url) as env:
        clock = env.reset(manifest['seed'], mode='sim')
        env.page.evaluate('research.setHuman(true)')
        for row in actions:
            clock = env.advance(row['visual_frame']-clock['visual_frame'])
            assert clock['frame'] == row['logical_frame']
            env.page.evaluate('(a)=>research.setHumanAction(a)', row['action'])
        clock = env.advance(expected['clock']['visual_frame']-clock['visual_frame'])
        state = env.diagnostics()['state']
        comparison=compare_engine_state(state,expected['state'])
        write(directory/'replay_diff.json',comparison)
        assert comparison['bounded_float'], 'Recorded state differs from replay beyond float tolerance'
    result = {'verified': True, 'status': state['status'], 'tick': state['tick'],
              'boss_hp': state['boss']['hp'], 'hits': state['hits'],
              'lives': state['player']['lives'], 'visual_frame': clock['visual_frame'],
              'exact':comparison['exact'],'bounded_float':comparison['bounded_float'],
              'max_abs_float_difference':comparison['max_abs_float_difference'],
              'float_abs_tolerance':comparison['float_abs_tolerance']}
    write(directory/'verification.json', result)
    return result


def extract(directory, frame, count=3):
    """PNG/frame/held only. Human future actions remain separate label files."""
    frames = [json.loads(s) for s in (directory/'frames.jsonl').read_text().splitlines()]
    chosen = [row for row in frames if row['frame'] <= frame][-count:]
    target = directory/'observations'/f'frame-{frame:05d}'
    target.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, row in enumerate(chosen):
        name = f'image_{i}.png';shutil.copyfile(directory/row['png'], target/name)
        rows.append({'frame': row['frame'], 'visual_frame': row['clock']['visual_frame'], 'held': row['held'], 'png': name, 'sha256': row['sha256']})
    write(target/'observation.json', {'source_run': directory.name,
          'observation_frame': chosen[-1]['frame'] if chosen else None,
          'images': rows, 'label_source': 'Human actions are stored separately; do not include future labels in model input.'})
    return str(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8796)
    parser.add_argument('--output', type=Path, default=Path('/tmp/kaguya-human-recordings'))
    parser.add_argument('--url', default='http://127.0.0.1:8796/game/')
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--extract', type=Path)
    parser.add_argument('--frame', type=int, default=0)
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify,args.url)));return
    if args.extract:
        print(extract(args.extract,args.frame));return
    args.output.mkdir(parents=True, exist_ok=True)
    dist = HERE.parent/'dist'
    assert hashlib.sha256((dist/'engine.mjs').read_bytes()).hexdigest() == ENGINE_HASH
    lock = threading.Lock()

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_):pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/':
                data = (HERE/'human_record.html').read_bytes()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            elif path.startswith('/game/'):
                self.directory = str(dist);self.path = self.path[len('/game'):];super().do_GET()
            elif path.startswith('/recordings/'):
                self.directory = str(args.output);self.path = self.path[len('/recordings'):];super().do_GET()
            else:self.send_error(404)

        def do_POST(self):
            try:
                url = urlsplit(self.path)
                raw = self.rfile.read(int(self.headers.get('Content-Length','0')))
                if url.path == '/api/video':
                    data = {'id':parse_qs(url.query)['id'][0]}
                else:data = json.loads(raw)
                with lock:
                    if url.path == '/api/start':
                        seed = data['seed'];assert type(seed) is int and 0 <= seed <= 4294967295
                        ident = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(3)
                        folder = args.output/ident;folder.mkdir();(folder/'frames').mkdir()
                        manifest = {'kind':'human_demonstration','provider':'human','seed':seed,'mode':'realtime','speed':1,'video_target_fps':30,'keyframe_stride':15,'created_at':datetime.now(timezone.utc).isoformat(),'complete':False}
                        write(folder/'manifest.json',manifest)
                        for name in ['key_edges.jsonl','actions.jsonl','frames.jsonl']:(folder/name).touch()
                        result = {'id':ident,'path':str(folder)}
                    else:
                        ident = data['id'];assert ident == Path(ident).name and ident not in ['.','..']
                        folder = args.output/ident;assert (folder/'manifest.json').is_file()
                        if url.path == '/api/events':
                            if 'batch_seq' in data:persist_event_batch(folder,data)
                            else:
                                for field,name in [('keys','key_edges.jsonl'),('actions','actions.jsonl')]:
                                    with (folder/name).open('a') as handle:
                                        for row in data[field]:handle.write(json.dumps(row)+'\n')
                        elif url.path == '/api/frames':
                            persist_frame_batch(folder,data['items'])
                        elif url.path == '/api/frame':
                            png = base64.b64decode(data.pop('png').split(',',1)[1]);assert png.startswith(b'\x89PNG\r\n\x1a\n')
                            name = f"frames/visual-{data['clock']['visual_frame']:06d}.png";(folder/name).write_bytes(png)
                            row = {'frame':data['frame'],'held':data['held'],'clock':data['clock'],'png':name,'sha256':hashlib.sha256(png).hexdigest()}
                            with (folder/'frames.jsonl').open('a') as handle:handle.write(json.dumps(row)+'\n')
                        elif url.path == '/api/video':
                            (folder/'human.webm').write_bytes(raw)
                        elif url.path == '/api/final':
                            write(folder/'final_state.json',{'state':data['state'],'clock':data['clock']})
                            manifest = json.loads((folder/'manifest.json').read_text());state=data['state']
                            manifest.update(complete=state['status']!='playing' and not data.get('staged_upload'),gameplay_complete=state['status']!='playing',core_uploads_complete=not data.get('staged_upload'),frame_uploads_complete=not data.get('staged_upload'),status=state['status'],tick=state['tick'],visual_frame=data['clock']['visual_frame'],boss_hp=state['boss']['hp'],hits=state['hits'],lives=state['player']['lives'],actual_visual_speed=data['clock']['actual_visual_speed'],blur_events=data['clock']['blur_events'])
                            edges=[json.loads(line) for line in (folder/'key_edges.jsonl').read_text().splitlines()]
                            manifest['pause_events']=sum(row['code']=='Escape' and row['down'] and row.get('paused',False) for row in edges)
                            write(folder/'manifest.json',manifest)
                        elif url.path == '/api/complete':
                            assert (folder/'human.webm').stat().st_size>0 and (folder/'final_state.json').is_file()
                            assert len(list((folder/'event_batches').glob('batch-*.json')))==data['event_batches']
                            manifest=json.loads((folder/'manifest.json').read_text());manifest.update(complete=manifest['gameplay_complete'],core_uploads_complete=True,frame_uploads_complete=bool(data['frames']))
                            edges=[json.loads(line) for line in (folder/'key_edges.jsonl').read_text().splitlines()]
                            manifest['pause_events']=sum(row['code']=='Escape' and row['down'] and row.get('paused',False) for row in edges)
                            write(folder/'manifest.json',manifest)
                        else:raise ValueError('Unknown endpoint')
                        result={'saved':True}
                body=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            except Exception as exc:self.send_error(400,str(exc))

    print(f'Human recorder: http://127.0.0.1:{args.port}/\nOutput: {args.output}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__ == '__main__':main()
