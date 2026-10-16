"""Offline paired outer-prompt benchmark; never a complete-game solve claim.

`prepare` captures identical actor payloads without model calls. `benchmark`
requires an explicit externally supplied native subscription provider factory.
Only this trusted post-response grader reads the chart. No actions are executed.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import random
import statistics
import time

from .model_env import ModelVisualEnv
from .model_lean_policy import prompt, parse

ROOT = Path(__file__).resolve().parents[2]
TIMESTEPS = (1., 1.4, 3.1, 5.2, 6., 7.8, 9.2, 12., 15., 17., 20.5, 23.2)
VARIANTS = ('baseline', 'minimal')


def sha(data):
    return hashlib.sha256(data).hexdigest()


async def prepare(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    memory_bytes = Path(args.memory).read_bytes()
    chart_path = Path(args.chart).resolve()
    inputs = []
    async with ModelVisualEnv(args.url, virtual=True, browser_executable=args.browser_executable,
                              chart_path=chart_path, clock_offset_ms=10000) as env:
        await env.start()
        for index, game_s in enumerate(TIMESTEPS):
            await env.advance(game_s)
            frame = await env.capture()
            snapshot = await env.snapshot()
            context = {'frames': [frame], 'external_now_ms': snapshot['clock_ms'],
                       'pending_plans': [], 'executed_acks': [], 'rtt_history_ms': [],
                       'request_version': index + 1, 'queue_version': snapshot['version'],
                       'model_memory': memory_bytes.decode()}
            text = prompt(context)
            image_name = f'input-{index:02d}.png'
            prompt_name = f'input-{index:02d}.txt'
            (output / image_name).write_bytes(frame['png'])
            (output / prompt_name).write_text(text)
            inputs.append({'index': index, 'image': image_name, 'prompt': prompt_name,
                           'image_sha256': sha(frame['png']), 'prompt_sha256': sha(text.encode()),
                           'capture_start_ms': frame['capture_start_ms'], 'capture_end_ms': frame['capture_end_ms'],
                           'external_now_ms': snapshot['clock_ms'], 'trusted_game_s': game_s})
    manifest = {'kind': 'offline_outer_ab_fixed_actor_inputs', 'clock_offset_ms': 10000,
                'memory_sha256': sha(memory_bytes), 'trusted_chart_path': str(chart_path),
                'trusted_chart_sha256': sha(chart_path.read_bytes()), 'inputs': inputs,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'source_sha256': {name: sha((ROOT / name).read_bytes()) for name in
                    ('experiments/rhythm/model_outer_ab.py', 'experiments/rhythm/model_lean_policy.py',
                     'experiments/rhythm/model_compact_policy.py', 'experiments/rhythm/model_policy.py',
                     'experiments/rhythm/model_env.py', 'dist/model-sim-clock.js', 'dist/model-executor.js', 'dist/game.js')},
                'paid_api_calls': 0, 'subscription_calls': 0,
                'boundary': 'Providers receive only the saved prompt string and PNG bytes, never this manifest or chart.'}
    (output / 'inputs.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'prepared_inputs': len(inputs), 'output': str(output), 'model_calls': 0}), flush=True)


def schedule_pairs(inputs, repeat, seed):
    rng = random.Random(seed)
    pairs = [(item['index'], iteration) for iteration in range(repeat) for item in inputs]
    rng.shuffle(pairs)
    return [{'input_index': index, 'repeat': iteration, 'order': rng.sample(list(VARIANTS), 2)}
            for index, iteration in pairs]


def grade(answer, item, chart, *, clock_offset_ms, full_return_s, api_delays=()):
    """Trusted offline comparison only; never feeds expected targets to actors."""
    try:
        plan = parse(answer)
    except (ValueError, TypeError) as error:
        return {'schema_valid': False, 'schema_error': type(error).__name__}
    note_times = [(index, 'dfjk'[note['lane']], clock_offset_ms + note['time'] * 1000)
                  for index, note in enumerate(chart['notes'])]
    # Visibility is evaluator metadata only, using the unchanged game's travel
    # and judgement windows. It never computes or adjusts an emitted action.
    visible = {index for index, note in enumerate(chart['notes'])
               if item['trusted_game_s'] - .18 <= note['time'] <= item['trusted_game_s'] + 1.8}
    records = []
    for tap in plan['taps']:
        candidates = [note for note in note_times if note[1] == tap['key']]
        nearest = min(candidates, key=lambda note: abs(note[2] - tap['at_ms'])) if candidates else None
        error = abs(nearest[2] - tap['at_ms']) if nearest else None
        records.append({'id': tap['id'], 'key': tap['key'], 'at_ms': tap['at_ms'], 'expires_ms': tap['expires_ms'],
                        'nearest_note_index': nearest[0] if nearest else None,
                        'expected_at_ms': nearest[2] if nearest else None, 'absolute_error_ms': error,
                        'within_55ms': error is not None and error <= 55,
                        'within_110ms': error is not None and error <= 110,
                        'within_180ms': error is not None and error <= 180,
                        'target_visible_in_input': nearest is not None and nearest[0] in visible,
                        'plan_lead_ms': tap['at_ms'] - item['external_now_ms'],
                        'hypothetical_return_lead_ms': tap['at_ms'] - (item['external_now_ms'] + full_return_s * 1000),
                        'unexpired_at_hypothetical_return': tap['expires_ms'] >= item['external_now_ms'] + full_return_s * 1000})
    covered = {row['nearest_note_index'] for row in records if row['within_180ms'] and row['target_visible_in_input']}
    result = {'schema_valid': True, 'plan': plan, 'empty': not records, 'tap_count': len(records),
            'visible_note_count': len(visible), 'covered_visible_notes_180ms': len(covered),
            'visible_coverage_180ms': len(covered) / len(visible) if visible else None,
            'duplicate_target_count': len([row for row in records if row['nearest_note_index'] is not None])
                                      - len({row['nearest_note_index'] for row in records if row['nearest_note_index'] is not None}),
            'tap_grades': records}
    if api_delays:
        covered_samples = {threshold: [] for threshold in (55, 110, 180)}
        useful = 0
        for row in records:
            row['api_unexpired_probability'] = 0.
            for threshold in covered_samples:
                row[f'api_within_{threshold}ms_probability'] = 0.
        for delay in api_delays:
            arrival = item['external_now_ms'] + delay * 1000
            covered = {threshold: set() for threshold in covered_samples}
            for row in records:
                # Offline generic-executor emulation only; never backdate a tap.
                actual = max(arrival, row['at_ms'])
                if actual > row['expires_ms']:
                    continue
                row['api_unexpired_probability'] += 1 / len(api_delays)
                if row['expected_at_ms'] is None:
                    continue
                error = abs(actual - row['expected_at_ms'])
                for threshold in covered:
                    if error <= threshold:
                        row[f'api_within_{threshold}ms_probability'] += 1 / len(api_delays)
                        if row['target_visible_in_input']:
                            covered[threshold].add(row['nearest_note_index'])
            useful += bool(covered[180])
            for threshold in covered:
                covered_samples[threshold].append(len(covered[threshold]) / len(visible) if visible else 0.)
        result['empirical_api'] = {'samples': len(api_delays),
            'any_visible_target_180ms_probability': useful / len(api_delays),
            'mean_visible_coverage': {str(threshold): statistics.mean(values) if visible else None for threshold, values in covered_samples.items()},
            'assumptions': 'Offline independent response; actual=max(arrival,model_at) until model_expiry. Excludes browser overhead and cross-response interactions.'}
    return result


def token_metrics(metadata):
    usage = metadata.get('token_usage', metadata.get('tokenUsage', {})) or {}
    last = usage.get('last', usage.get('total', usage)) or {}
    return {key: last.get(key) for key in ('inputTokens', 'cachedInputTokens', 'cacheWriteInputTokens',
                                          'outputTokens', 'reasoningOutputTokens', 'totalTokens')}


async def benchmark(args):
    if args.repeat < 1 or args.pairs_concurrency not in (1, 2):
        raise ValueError('Use positive repeat and one or two concurrent pairs')
    source = Path(args.inputs).resolve()
    manifest = json.loads((source / 'inputs.json').read_text())
    chart_bytes = Path(manifest['trusted_chart_path']).read_bytes()
    if sha(chart_bytes) != manifest['trusted_chart_sha256']:
        raise ValueError('Trusted chart changed after input capture')
    chart = json.loads(chart_bytes)
    api_delays = []
    if args.api_profile:
        distribution = json.loads(Path(args.api_profile).read_text())
        api_delays = [row['metadata']['latency_s'] for row in distribution['rows'] if row.get('status') == 'completed']
        if not api_delays or any(type(value) not in (int, float) or not 0 < value < float('inf') for value in api_delays):
            raise ValueError('API distribution requires finite positive completed RTTs; retain all tails')
    inputs = {item['index']: item for item in manifest['inputs']}
    payloads = {}
    for index, item in inputs.items():
        text, png = (source / item['prompt']).read_text(), (source / item['image']).read_bytes()
        if sha(text.encode()) != item['prompt_sha256'] or sha(png) != item['image_sha256']:
            raise ValueError('Saved A/B input bytes changed')
        payloads[index] = (text, png)
    module_name, factory_name = args.provider.split(':', 1)
    module = importlib.import_module(module_name)
    factory = getattr(module, factory_name)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    pair_plan = schedule_pairs(list(inputs.values()), args.repeat, args.seed)
    config = {'kind': 'offline_paired_outer_prompt_ab', 'variants': list(VARIANTS), 'repeat': args.repeat,
              'pairs': pair_plan, 'seed': args.seed, 'pairs_concurrency': args.pairs_concurrency,
              'actor_capacity_per_variant': args.pairs_concurrency,
              'input_manifest_sha256': sha((source / 'inputs.json').read_bytes()),
              'provider': args.provider, 'provider_source_sha256': sha(Path(module.__file__).read_bytes()),
              'harness_sha256': sha(Path(__file__).read_bytes()),
              'empirical_api_distribution': {'path': str(Path(args.api_profile).resolve()), 'sha256': sha(Path(args.api_profile).read_bytes()), 'samples': len(api_delays)} if api_delays else None,
              'paid_api_calls': 0, 'claim': 'Offline screenshot accuracy and full-return latency only; not a complete-game solve.'}
    (output / 'config.json').write_text(json.dumps(config, indent=2))
    pools = {variant: asyncio.Queue() for variant in VARIANTS}
    providers = []
    results = []
    semaphore = asyncio.Semaphore(args.pairs_concurrency)
    try:
        for variant in VARIANTS:
            for _ in range(args.pairs_concurrency):
                provider = await factory(variant).start()
                providers.append(provider)
                configuration = getattr(provider, 'configuration', {})
                if configuration.get('auth') != 'chatgpt' or configuration.get('variant') != variant:
                    raise ValueError('Provider must confirm ChatGPT auth and requested outer variant')
                config.setdefault('provider_configurations', []).append(configuration)
                (output / 'config.json').write_text(json.dumps(config, indent=2))
                pools[variant].put_nowait(provider)

        async def pair(pair_index, settings):
            async with semaphore:
                item = inputs[settings['input_index']]
                text, png = payloads[item['index']]
                for order_index, variant in enumerate(settings['order']):
                    provider = await pools[variant].get()
                    row = {'pair_index': pair_index, **settings, 'order_index': order_index, 'variant': variant,
                           'prompt_sha256': item['prompt_sha256'], 'image_sha256': item['image_sha256']}
                    started = time.perf_counter()
                    try:
                        # Same exact string and byte object for BOTH outer variants.
                        answer, metadata = await provider.act(text, [png])
                        elapsed = time.perf_counter() - started
                        row.update(answer=answer, metadata=metadata, full_return_s=elapsed,
                                   token_metrics=token_metrics(metadata),
                                   grade=grade(answer, item, chart, clock_offset_ms=manifest['clock_offset_ms'], full_return_s=elapsed, api_delays=api_delays))
                    except Exception as error:
                        row.update(full_return_s=time.perf_counter()-started, error=type(error).__name__ + ': ' + str(error)[:250])
                    finally:
                        pools[variant].put_nowait(provider)
                    results.append(row)
                    with (output / 'responses.jsonl').open('a') as handle:
                        handle.write(json.dumps(row) + '\n')
                    print('OUTER_AB_SAMPLE ' + json.dumps({key: row.get(key) for key in ('pair_index', 'variant', 'full_return_s', 'error')}), flush=True)

        await asyncio.gather(*(pair(index, settings) for index, settings in enumerate(pair_plan)))
    finally:
        await asyncio.gather(*(provider.close() for provider in providers), return_exceptions=True)
    summaries = {}
    for variant in VARIANTS:
        rows = [row for row in results if row['variant'] == variant]
        complete = [row for row in rows if 'answer' in row]
        timings = [row['full_return_s'] for row in complete]
        taps = [tap for row in complete for tap in row.get('grade', {}).get('tap_grades', [])]
        summaries[variant] = {'calls': len(rows), 'completed': len(complete), 'errors': len(rows)-len(complete),
                              'median_full_return_s': statistics.median(timings) if timings else None,
                              'max_full_return_s': max(timings) if timings else None,
                              'schema_valid': sum(row['grade']['schema_valid'] for row in complete),
                              'empty_answers': sum(row.get('grade', {}).get('empty', False) for row in complete),
                              'tap_count': len(taps), 'within_55ms': sum(tap['within_55ms'] for tap in taps),
                              'within_110ms': sum(tap['within_110ms'] for tap in taps),
                              'within_180ms': sum(tap['within_180ms'] for tap in taps)}
    paired = []
    for index in range(len(pair_plan)):
        group = {row['variant']: row for row in results if row['pair_index'] == index and 'answer' in row}
        if set(group) == set(VARIANTS):
            paired.append({'pair_index': index, 'minimal_minus_baseline_s': group['minimal']['full_return_s'] - group['baseline']['full_return_s']})
    summary = {'offline_only': True, 'solve_claim': False, 'variants': summaries,
               'paired_latency_differences': paired, 'paid_api_calls': 0}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2))
    print('OUTER_AB_COMPLETE ' + json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    capture = commands.add_parser('prepare')
    capture.add_argument('--url', default='http://127.0.0.1:18891')
    capture.add_argument('--browser-executable')
    capture.add_argument('--memory', required=True)
    capture.add_argument('--chart', default=str(ROOT/'dist/chart.json'))
    capture.add_argument('--output', required=True)
    run = commands.add_parser('benchmark')
    run.add_argument('--inputs', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--provider', required=True, help='Native-only module:factory accepting baseline/minimal')
    run.add_argument('--repeat', type=int, default=2)
    run.add_argument('--api-profile', help='Real API RTT distribution for paired offline timeliness grading')
    run.add_argument('--seed', type=int, default=17)
    run.add_argument('--pairs-concurrency', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    asyncio.run(prepare(args) if args.command == 'prepare' else benchmark(args))
