"""Frozen-image prompt evaluation via existing native subscription runner only."""
import argparse
import base64
import concurrent.futures
import hashlib
import json
import pathlib
import random
import re
import sys
import threading


def run(args):
    payload = json.loads(args.tasks.read_text())
    if not isinstance(payload, list) or not payload:
        raise ValueError('Expected nonempty task list')
    keys = {(t['variant'], t['case_id'], t['repeat']) for t in payload}
    if len(keys) != len(payload):
        raise ValueError('Duplicate evaluation tasks')
    for t in payload:
        if re.fullmatch(r'C\d{2}[ab]', t['case_id']) is None or len(t['images']) != 3:
            raise ValueError('Only three-image core cases are allowed')
    random.Random(20261015).shuffle(payload)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'protocol.json').write_text(json.dumps({
        'auth': 'ChatGPT subscription', 'direct_api_calls': 0,
        'task_count':len(payload),'workers':args.workers,
        'quota_stop_percent':args.quota_stop_percent,
        'tasks_sha256':hashlib.sha256(args.tasks.read_bytes()).hexdigest(),
        'scoring':'posthoc human candidate-set agreement; not survival accuracy',
        'controller':'no controller application in frozen-image evaluation'
    }, indent=2))
    sys.path.insert(0, str(args.source))
    from subscription_client import SubscriptionClient
    from subscription_quota import read_limits, require_headroom
    local = threading.local()
    clients = []
    mutex = threading.Lock()
    stopped = threading.Event()

    def evaluate(task):
        if stopped.is_set():
            return
        if not hasattr(local, 'client'):
            with mutex:
                worker = len(clients)
                client = SubscriptionClient(args.suite,args.output/f'worker-{worker}',
                                            quota_stop_percent=args.quota_stop_percent)
                if client.runner.settings.get('model') != 'gpt-6.1-sol':
                    client.close()
                    raise RuntimeError('Frozen gpt-6.1-sol model required')
                local.client = client
                clients.append(client)
        client = local.client
        directory = args.output / f"{task['variant']}-{task['case_id']}-{task['repeat']}"
        directory.mkdir()
        quota = read_limits(client.runner, directory/'quota-request.json')
        require_headroom(quota,args.quota_stop_percent)
        if stopped.is_set():
            return
        images = []
        for uri in task['images']:
            prefix = 'data:image/png;base64,'
            if not uri.startswith(prefix):
                raise ValueError('Expected PNG data URI')
            images.append(base64.b64decode(uri[len(prefix):],validate=True))
        answer, meta = client.act(task['prompt'],images,directory/'call')
        action = int(answer.strip()) if re.fullmatch(r'[0-8]',answer.strip()) else None
        record = {k:task[k] for k in ['variant','case_id','repeat']}
        record.update(answer=answer,action=action,meta=meta,quota_before=quota,
                      prompt_sha256=hashlib.sha256(task['prompt'].encode()).hexdigest(),
                      image_sha256=[hashlib.sha256(im).hexdigest() for im in images],
                      model=client.runner.settings.get('model'),
                      reasoning_effort=client.runner.settings.get('reasoning_effort'))
        with mutex:
            with (args.output/'results.jsonl').open('a') as handle:
                handle.write(json.dumps(record)+'\n')
            print(json.dumps({k:record[k] for k in ['variant','case_id','repeat','action']}),flush=True)
    errors = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending = [pool.submit(evaluate,t) for t in payload]
            for future in concurrent.futures.as_completed(pending):
                try:
                    future.result()
                except Exception as exc:
                    stopped.set()
                    for other in pending:
                        other.cancel()
                    errors.append(type(exc).__name__+': '+str(exc))
    finally:
        for client in clients:
            client.close()
        (args.output/'completion.json').write_text(json.dumps({'errors':errors,'stopped':stopped.is_set()}))
    if errors:
        raise RuntimeError(errors[0])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',type=pathlib.Path,required=True)
    parser.add_argument('--suite',type=pathlib.Path,required=True)
    parser.add_argument('--tasks',type=pathlib.Path,required=True)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    parser.add_argument('--workers',type=int,choices=range(1,9),default=3)
    parser.add_argument('--quota-stop-percent',type=int,choices=range(1,51),default=50)
    run(parser.parse_args())
