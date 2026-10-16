"""Bounded paid transfer probe: eight serial calls, then 24 calls at concurrency eight.

Uses frozen, hash-checked inputs exported from completed trajectories. No game or
subscription runner is started. API credentials stay in memory and are never logged.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, ROUND_CEILING
import getpass
import hashlib
import json
import os
from pathlib import Path
import statistics
import threading
import time

MODEL = 'gpt-6.1-sol'
TIER = 'ultrafast'
PROMPT_HASH = 'ce25ef4a60efe2c58e699e191495a4bd99d9c58e2f9cd4c8f2126f598d364112'
OUTPUT_LIMIT = 256
LIMIT_MICRO_USD = 1_000_000


def payload(sample):
    return {'model': MODEL, 'service_tier': TIER, 'reasoning': {'effort': 'low'},
            'text': {'verbosity': 'low'}, 'store': False, 'stream': True,
            'max_output_tokens': OUTPUT_LIMIT, 'input': sample['input']}


def reserve_bound(input_tokens):
    if type(input_tokens) is not int or not 0 < input_tokens < 8192:
        raise ValueError('Unexpected input count; abort before inference')
    # Input counted by provider; add 10% plus 128 tokens of safety margin.
    # Reserve all input at the highest short-context rate (cache writes).
    tokens = (input_tokens * 11 + 9) // 10 + 128
    return tokens * 15 + OUTPUT_LIMIT * 60


def usage_cost(usage):
    i, o = usage['input_tokens'], usage['output_tokens']
    details = usage.get('input_tokens_details') or {}
    c, w = details.get('cached_tokens', 0), details.get('cache_write_tokens', 0)
    if any(type(x) is not int or x < 0 for x in (i, o, c, w)) or c + w > i:
        raise ValueError('Invalid usage')
    value = Decimal(i-c-w)*12 + Decimal(c)*Decimal('0.6') + Decimal(w)*15 + Decimal(o)*60
    return int(value.to_integral_value(rounding=ROUND_CEILING))


class Ledger:
    def __init__(self, bounds, path, prior_used=0):
        if type(prior_used) is not int or prior_used < 0 or sum(bounds)+prior_used > LIMIT_MICRO_USD:
            raise ValueError('Whole experiment worst-case reservation exceeds USD 1')
        self.pending = dict(enumerate(bounds))
        self.used = prior_used
        self.stopped = False
        self.path = path
        self.lock = threading.Lock()
        self.log({'event': 'reserve_entire_plan', 'micro_usd': sum(bounds), 'prior_used_micro_usd': prior_used,
                  'requests': len(bounds), 'limit_micro_usd': LIMIT_MICRO_USD})

    def log(self, event):
        with self.path.open('a') as f:
            f.write(json.dumps(event)+'\n')

    def settle(self, ticket, usage):
        with self.lock:
            bound = self.pending.pop(ticket)
            try:
                actual = usage_cost(usage)
            except (KeyError, TypeError, ValueError):
                actual = bound
                self.stopped = True
            if actual > bound:
                self.stopped = True
            self.used += actual
            self.log({'event': 'settle', 'ticket': ticket,
                      'micro_usd': actual, 'uncertain_charge_reserved': usage is None,
                      'stopped': self.stopped})

    def cancel_unstarted(self, ticket):
        with self.lock:
            self.pending.pop(ticket)
            self.log({'event': 'cancel_unstarted', 'ticket': ticket})


def validate_inputs(data):
    if data['base_prompt_sha256'] != PROMPT_HASH or len(data['samples']) != 24:
        raise ValueError('Wrong frozen input set')
    for sample in data['samples']:
        content = sample['input'][0]['content']
        prompt = content[0]['text']
        if hashlib.sha256(prompt.encode()).hexdigest() != sample['prompt_sha256']:
            raise ValueError('Prompt hash mismatch')
        images = content[1:]
        if len(images) != 3:
            raise ValueError('Expected exactly three images')
        for part, expected in zip(images, sample['image_sha256']):
            if part['type'] != 'input_image' or part['detail'] != 'low':
                raise ValueError('Changed image specification')
            raw = base64.b64decode(part['image_url'].split(',', 1)[1], validate=True)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError('Image hash mismatch')


def stats(rows):
    good = [r for r in rows if r['status'] == 'completed' and r.get('action_valid')]
    values = sorted(r['request_s'] for r in good)
    ttft = [r['ttft_s'] for r in good if r.get('ttft_s') is not None]
    return {'attempts': len(rows), 'valid_completed': len(good),
            'mean_s': statistics.mean(values) if values else None,
            'p50_s': statistics.median(values) if values else None,
            'p95_s': values[(95*len(values)+99)//100-1] if values else None,
            'max_s': max(values) if values else None,
            'mean_ttft_s': statistics.mean(ttft) if ttft else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-paid', action='store_true')
    parser.add_argument('--prompt-for-key', action='store_true')
    parser.add_argument('--prior-results', type=Path,
                        help='Carry all charged or conservatively reserved costs from a stopped pilot')
    args = parser.parse_args()
    data = json.loads(args.inputs.read_text())
    validate_inputs(data)
    samples = data['samples']
    serial = [samples[i] for i in range(0, 24, 3)]
    plan = [('serial', s) for s in serial] + [('parallel8', s) for s in samples]
    prior_used = 0
    if args.prior_results:
        previous = json.loads((args.prior_results/'summary.json').read_text())
        if previous['unsettled_reserved_usd'] != 0:
            raise SystemExit('Prior calls are unsettled; do not start another paid run')
        events = [json.loads(line) for line in (args.prior_results/'budget.jsonl').read_text().splitlines()]
        initial = events[0].get('prior_used_micro_usd', 0)
        prior_used = initial + sum(e['micro_usd'] for e in events if e['event']=='settle')
        if Decimal(str(previous['accounted_usd']))*1_000_000 != prior_used:
            raise SystemExit('Prior summary and ledger disagree')
    if not args.run_paid:
        print(json.dumps({'status': 'inputs_validated_no_api_calls',
                          'serial_requests': 8, 'parallel_requests': 24,
                          'concurrency': 8, 'model': MODEL, 'tier': TIER,
                          'budget_usd': 1, 'output_token_limit': OUTPUT_LIMIT}))
        return
    key = getpass.getpass('API key (memory only): ') if args.prompt_for_key else os.environ.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit('Missing OPENAI_API_KEY; no network calls made')
    import requests
    args.output.mkdir(parents=True, exist_ok=False)
    headers = {'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'}
    rows = []
    bounds_by_sample = {}
    # Count exact image and text input before reserving any inference requests.
    with requests.Session() as session:
        for sample in samples:
            r = session.post('https://api.openai.com/v1/responses/input_tokens',
                             headers=headers, json={'model': MODEL, 'input': sample['input']},
                             timeout=(10, 30))
            if r.status_code != 200:
                raise SystemExit('Token-count preflight HTTP '+str(r.status_code)+'; no inference dispatched')
            count = r.json()['input_tokens']
            bounds_by_sample[sample['sample_id']] = {'input_tokens': count, 'bound': reserve_bound(count)}
    bounds = [bounds_by_sample[s['sample_id']]['bound'] for _, s in plan]
    ledger = Ledger(bounds, args.output/'budget.jsonl', prior_used)
    protocol = {'model': MODEL, 'tier': TIER, 'effort': 'low', 'max_output_tokens': OUTPUT_LIMIT,
                'budget_usd': 1, 'whole_plan_reserved_usd': sum(bounds)/1e6,
                'prior_accounted_usd': prior_used/1e6,
                'serial_requests': 8, 'parallel_requests': 24, 'parallel_capacity': 8,
                'transport': 'HTTPS SSE; one persistent session per worker',
                'inputs_sha256': hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
                'counts': bounds_by_sample, 'source_round': data['source_round'],
                'scope': 'fixed-input latency probe; no live gameplay',
                'limitations': ['Serial precedes parallel; cache and connection warmup may affect comparison.',
                                'P95 is descriptive for this small sample.',
                                f'A {OUTPUT_LIMIT}-token cap can produce incomplete responses; these count as failures.']}
    (args.output/'protocol.json').write_text(json.dumps(protocol, indent=2)+'\n')
    print('PREFLIGHT '+json.dumps({'reserved_usd': sum(bounds)/1e6, 'prior_accounted_usd': prior_used/1e6,
                                 'total_worst_case_usd': (sum(bounds)+prior_used)/1e6,
                                 'requests': len(plan)}), flush=True)
    local = threading.local()
    lock = threading.Lock()
    stop = threading.Event()
    active = 0
    peak = 0
    sessions = []

    def call(ticket, barrier=None):
        nonlocal active, peak
        phase, sample = plan[ticket]
        if stop.is_set() or ledger.stopped:
            ledger.cancel_unstarted(ticket)
            return {'ticket': ticket, 'phase': phase, 'status': 'skipped_before_dispatch'}
        if not hasattr(local, 'http'):
            local.http = requests.Session()
            with lock:
                sessions.append(local.http)
        if barrier:
            barrier.wait(timeout=15)
        usage = None
        response = None
        ttft = None
        row = {'ticket': ticket, 'phase': phase, 'sample_id': sample['sample_id']}
        with lock:
            active += 1
            peak = max(peak, active)
        started = time.perf_counter()
        row['started_monotonic'] = started
        try:
            with local.http.post('https://api.openai.com/v1/responses', headers=headers,
                                 json=payload(sample), stream=True, timeout=(10, 45)) as r:
                if r.status_code != 200:
                    raise RuntimeError('HTTP '+str(r.status_code))
                for line in r.iter_lines(chunk_size=1):
                    if not line.startswith(b'data: ') or line[6:] == b'[DONE]':
                        continue
                    event = json.loads(line[6:])
                    kind = event.get('type')
                    if kind == 'response.output_text.delta' and ttft is None:
                        ttft = time.perf_counter()-started
                    if kind in ('response.completed', 'response.failed', 'response.incomplete'):
                        response = event['response']
                        usage = response.get('usage')
                        break
            row.update(request_s=time.perf_counter()-started, ttft_s=ttft)
            if not response:
                raise RuntimeError('Stream ended without terminal response')
            answer = ''.join(c.get('text', '') for x in response.get('output', [])
                             if x['type'] == 'message' for c in x.get('content', []) if c['type'] == 'output_text')
            row.update(status=response['status'], answer=answer, usage=usage,
                       model=response.get('model'), tier=response.get('service_tier'),
                       action_valid=answer.strip() in tuple(str(i) for i in range(9)))
            if row['model'] != MODEL or row['tier'] != TIER:
                raise RuntimeError('Unexpected model or tier; stop dispatch')
            if row['status'] != 'completed' or not row['action_valid']:
                stop.set()
        except Exception as exc:
            row.update(status='error', error_type=type(exc).__name__,
                       error=str(exc) if isinstance(exc, RuntimeError) else 'Transport or parsing error',
                       request_s=time.perf_counter()-started, ttft_s=ttft)
            stop.set()
        finally:
            ledger.settle(ticket, usage)
            with lock:
                active -= 1
                with (args.output/'requests.jsonl').open('a') as f:
                    f.write(json.dumps(row)+'\n')
        return row

    try:
        for ticket in range(8):
            rows.append(call(ticket))
            print('SERIAL '+json.dumps({'completed': len(rows), 'accounted_usd': ledger.used/1e6}), flush=True)
        barrier = threading.Barrier(8)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(call, ticket, barrier if ticket < 16 else None) for ticket in range(8, 32)]
            for future in as_completed(futures):
                rows.append(future.result())
        a, b = stats([r for r in rows if r['phase']=='serial']), stats([r for r in rows if r['phase']=='parallel8'])
        result = {'serial': a, 'parallel8': b, 'peak_client_inflight': peak,
                  'parallel_to_serial_mean_ratio': b['mean_s']/a['mean_s'] if a['mean_s'] and b['mean_s'] else None,
                  'accounted_usd': ledger.used/1e6, 'unsettled_reserved_usd': sum(ledger.pending.values())/1e6,
                  'budget_guard_stopped': ledger.stopped, 'stopped_on_error': stop.is_set(),
                  'scope': protocol['scope'], 'limitations': protocol['limitations']}
        (args.output/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
        print('DONE '+json.dumps(result), flush=True)
    finally:
        for session in sessions:
            session.close()
        headers.clear()
        key = None


if __name__ == '__main__':
    main()
