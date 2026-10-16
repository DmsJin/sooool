"""Serial paid profiling of direct native actions on raw saved camera inputs."""
import argparse
import base64
import getpass
import hashlib
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from paid import API, Budget, MODEL, TIER, valid_usage
from direct_io import prompt, parse


def stats(values):
    if not values:
        return None
    x = sorted(values)
    return {'n': len(x), 'min_s': x[0], 'mean_s': statistics.mean(x),
            'p50_s': statistics.median(x), 'p95_s': x[(95 * len(x) + 99) // 100 - 1]}


def prepare(source, calls):
    summary = json.loads((source / 'summary.json').read_text())
    if not summary['finished'] or summary.get('failure'):
        raise ValueError('Need a complete historical source, not a partial episode')
    # Native public spec only. This fresh training-seed world does not advance;
    # no candidate/reference-player methods are used to construct observations.
    from core.episode import load_plugin, header_cfg
    from core.local import seat_spec
    plugin = str(ROOT / 'sports/tabletennis/plugin.py')
    sport = load_plugin(plugin)
    cfg = header_cfg(json.loads((source / 'episode.jsonl').read_text().splitlines()[0]))
    spec = seat_spec(sport, cfg, 'A', plugin=plugin)
    groups = {k: [] for k in ('serve_wait', 'serve_open', 'serve_tossed', 'incoming', 'outgoing')}
    for parent in sorted((source / 'observations').glob('*.json')):
        saved = json.loads(parent.read_text())
        state, seq = saved['state'], saved['seq']
        if state.get('you_serve') and state.get('ball_state') == 'your serve':
            phase = state.get('serve', {}).get('phase')
            kind = 'serve_tossed' if phase == 'tossed' else 'serve_open' if phase == 'open' else 'serve_wait'
        elif state.get('ball_state') == 'coming to you' and state.get('ball_in_play'):
            kind = 'incoming'
        elif state.get('ball_state') == 'going to the opponent':
            kind = 'outgoing'
        else:
            continue
        image = source / 'observations' / f'{seq:05d}.png'
        worker = source / f'decision_{seq:05d}' / 'input.json'
        if not image.exists() or not worker.exists():
            continue
        png = image.read_bytes()
        if hashlib.sha256(png).hexdigest() != saved['image_sha256']:
            raise ValueError('Historical image integrity mismatch')
        old_text = json.loads(worker.read_text())['params']['input'][0]['text']
        if hashlib.sha256(old_text.encode()).hexdigest() != saved['prompt_sha256']:
            raise ValueError('Historical parent/worker prompt mismatch')
        # Recover camera timestamps only. Old prompt/policy/menus/answers never
        # enter the direct model input; direct_io applies the public whitelist.
        meta, _ = json.JSONDecoder().raw_decode(old_text.split('\nIMAGE_META ', 1)[1])
        groups[kind].append({'seq': seq, 'kind': kind, 'state': state,
                             'meta': meta, 'image': png})
    rng = random.Random(170116)
    if any(not g for g in groups.values()):
        raise ValueError('Missing a required observation category')
    for g in groups.values():
        rng.shuffle(g)
    selected = []
    while len(selected) < calls and any(groups.values()):
        for group in groups.values():
            if group and len(selected) < calls:
                selected.append(group.pop())
    if len(selected) != calls:
        raise ValueError('Too few distinct raw observations')
    rng.shuffle(selected)
    return selected, summary, spec


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--calls', type=int, default=12)
    p.add_argument('--slowdown', type=float, default=2)
    p.add_argument('--stage-ceiling', type=float, default=3)
    p.add_argument('--run-paid', action='store_true')
    a = p.parse_args()
    if not 6 <= a.calls <= 24:
        raise ValueError('Use 6 to 24 serial observations')
    samples, summary, spec = prepare(a.source, a.calls)
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'public_spec.json').write_text(json.dumps(spec, indent=2))
    # Explicit prior guidance, never the future latency of this request.
    timing = {'slowdown': a.slowdown, 'profile': 'prior menu-call measurements; direct output latency is being measured',
              'p50_wall_s': 1.149376814, 'p95_wall_s': 3.014958788,
              'p50_game_s': 1.149376814 / a.slowdown, 'p95_game_s': 3.014958788 / a.slowdown}
    for sample in samples:
        sample['text'] = prompt({'state': sample['state'], 'observation': sample['meta']}, spec, timing, 'direct_v1')
        d = a.output / f"input_{sample['seq']:05d}"
        d.mkdir()
        (d / 'image.png').write_bytes(sample['image'])
        (d / 'prompt.txt').write_text(sample['text'])
    plan = {'model': MODEL, 'service_tier': TIER, 'concurrency': 1, 'variant': 'direct_v1',
            'target_slowdown': a.slowdown,
            'source_hashes': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                              for name in ('profile_direct.py', 'direct_io.py', 'paid.py')},
            'source': str(a.source), 'source_digest': summary['digest'],
            'scope': 'New direct-action prompts on raw historical camera/state; no menu or inferred ball input; no gameplay performance claim',
            'samples': [{'seq': s['seq'], 'kind': s['kind'], 'prompt_sha256': hashlib.sha256(s['text'].encode()).hexdigest(),
                         'image_sha256': hashlib.sha256(s['image']).hexdigest()} for s in samples]}
    (a.output / 'plan.json').write_text(json.dumps(plan, indent=2))
    if not a.run_paid:
        print(json.dumps({'paid_calls': 0, **plan}))
        return
    api = API(getpass.getpass('API key (memory only): '), Budget(a.ledger), 'profiling', a.stage_ceiling)
    rows = []
    try:
        for sample in samples:
            notifications = []
            if len(sample['text'].encode()) > 12000:
                raise ValueError('Direct prompt exceeds audited input reservation shape')
            data = [{'role': 'user', 'content': [{'type': 'input_text', 'text': sample['text']},
                    {'type': 'input_image', 'detail': 'high', 'image_url': 'data:image/png;base64,' + base64.b64encode(sample['image']).decode()}]}]
            row = api.call(data, count=20000, max_output=512, action_parser=parse, on_ready=notifications.append)
            row.update(seq=sample['seq'], source_kind=sample['kind'], concurrency=1,
                       action_contract_valid=not row['error'], readiness_notifications=len(notifications))
            try: row['returned_action_type'] = parse(row['answer'])['type']
            except ValueError: row['returned_action_type'] = 'invalid'
            rows.append(row)
            with (a.output / 'requests.jsonl').open('a') as f:
                f.write(json.dumps(row) + '\n')
            print(json.dumps({k: row[k] for k in ('seq', 'source_kind', 'action_ready_s', 'request_s', 'error', 'cost_usd')}), flush=True)
            contract_error = (row['error'] or '').endswith('Terminal action is invalid or differs from ready action')
            wire_ok = row['status'] == 'completed' and row['model'] == MODEL and row['tier'] == TIER and valid_usage(row['usage'])
            if not wire_ok or (row['error'] and not contract_error):
                break
    finally:
        api.http.close()
    # Keep malformed outputs in the timing distribution at terminal time. Never
    # cherry-pick fast successful actions or silently repair invalid numbers.
    usable = len(rows) == len(samples) and all(r['status'] == 'completed' and valid_usage(r['usage']) and r['model'] == MODEL and r['tier'] == TIER and (not r['error'] or r['error'].endswith('Terminal action is invalid or differs from ready action')) for r in rows)
    delays = [(r['action_ready_s'] if not r['error'] else r['request_s']) for r in rows] if usable else []
    report = {'scope': plan['scope'], 'model': MODEL, 'service_tier': TIER, 'concurrency': 1,
              'variant': 'direct_v1', 'attempts': len(rows), 'valid_actions': sum(not r['error'] for r in rows),
              'target_slowdown': a.slowdown,
              'action_type_counts': {k: sum(r['returned_action_type'] == k for r in rows) for k in ('wait', 'move', 'toss', 'act', 'none', 'invalid')},
              'by_action_type': {k: stats([r['request_s'] for r in rows if r['returned_action_type'] == k]) for k in ('wait', 'move', 'toss', 'act', 'none', 'invalid')},
              'usable_for_simulation': usable, 'delays_s': delays,
              'p50_s': statistics.median(delays) if delays else None,
              'p95_s': stats(delays)['p95_s'] if delays else None,
              'latency': stats(delays), 'cost_usd': sum(r['cost_usd'] for r in rows),
              'invalid_action_timing': 'Full completion retained, not omitted',
              'source_kind_counts': {k: sum(r['source_kind'] == k for r in rows) for k in ('serve_wait', 'serve_open', 'serve_tossed', 'incoming', 'outgoing')}}
    (a.output / 'profile.json').write_text(json.dumps(report, indent=2))
    print('SUMMARY', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
