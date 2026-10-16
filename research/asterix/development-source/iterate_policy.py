"""Bounded adaptive policy screening, frozen three-seed rounds, subscription only."""
import argparse
import fcntl
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

from subscription_client import SubscriptionClient
from subscription_quota import read_limits, require_headroom

SEEDS = [2, 5, 6]
AXES = ('mid', 'brake', 'robust')


def add_axis(variant, axis):
    parts = set(variant.removeprefix('guard_intercept').strip('_').split('_'))
    parts.discard('')
    if axis not in AXES or not parts.issubset(AXES):
        raise ValueError('Unknown intercept policy axis')
    parts.add(axis)
    return 'guard_intercept' + ''.join('_' + x for x in AXES if x in parts)


def promote(candidate, champion):
    """Development screening only; paired wins are not a significance test."""
    if candidate.get('mean_score') is None or champion.get('mean_score') is None:
        return False
    new = {e['seed']: e['score'] for e in candidate['episodes']}
    old = {e['seed']: e['score'] for e in champion['episodes']}
    if sorted(new) != SEEDS or sorted(old) != SEEDS:
        return False
    return (candidate['mean_score'] >= champion['mean_score'] * 1.05
            and sum(new[s] > old[s] for s in SEEDS) >= 2
            and min(new.values()) >= min(old.values()) * 0.8)


def active_evaluators(output):
    pids = []
    for path in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = path.read_bytes().split(b'\0')
        except OSError:
            continue
        if str(output).encode() in args and any(a.endswith(b'/evaluate_dev.py') for a in args):
            pids.append(int(path.parent.name))
    return pids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', type=pathlib.Path, required=True)
    parser.add_argument('--profile', type=pathlib.Path, required=True)
    parser.add_argument('--baseline', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=args.resume)
    lock = (root / 'controller.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    source = root / 'source'
    if not args.resume:
        source.mkdir()
        for name in ('iterate_policy.py', 'evaluate_dev.py', 'simulate_async.py', 'simulate.py',
                     'chunk_control.py', 'subscription_client.py', 'subscription_quota.py',
                     'track_dev.py', 'track_iterations.py'):
            shutil.copyfile(pathlib.Path(__file__).with_name(name), source / name)
        profile = json.loads(args.profile.read_text())
        (root / 'profile').mkdir()
        for name in (args.profile.name, profile['distribution_path'], profile['burst_model_path']):
            shutil.copyfile(args.profile.parent / name, root / 'profile' / name)
        previous = json.loads(args.baseline.read_text())
        baseline = next(r for r in previous['rounds'] if r['variant'] == 'guard_intercept')
        if sorted(e['seed'] for e in baseline['episodes']) != SEEDS or baseline['mean_score'] is None:
            raise ValueError('Complete three-seed intercept baseline required')
        state = {'status': 'running', 'baseline': baseline, 'baseline_source': str(args.baseline),
                 'baseline_is_historical': True, 'best': baseline, 'dev_seeds': SEEDS,
                 'held_out_seeds': [7, 8, 9], 'rounds': [], 'round_outputs': [],
                 'max_rounds': 5, 'max_decisions_per_episode': 900,
                 'target_mean': 1500, 'max_game_seconds': 60, 'speed_fraction': 0.125,
                 'virtual_capacity': 8, 'actual_model_concurrency': 3, 'api_spend_usd': 0,
                 'profile_name': args.profile.name,
                 'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in source.glob('*.py')}}
    else:
        state = json.loads((root / 'status.json').read_text())

    def save():
        path = root / 'status.tmp'
        path.write_text(json.dumps(state, indent=2) + '\n')
        path.replace(root / 'status.json')

    save()
    (root / 'runtime').mkdir(exist_ok=True)
    client = None
    try:
        client = SubscriptionClient(args.suite, pathlib.Path(tempfile.mkdtemp(dir=root / 'runtime')))
        quota = read_limits(client.runner, root / 'runtime' / 'quota_request.json')
        if not args.resume:
            state['initial_quota'] = quota
            state['quota_stop_percent'] = min(70, int(quota['max_used_percent']) + 15)
        require_headroom(quota, state['quota_stop_percent'])
        state['status'] = 'running'
        save()

        def round_(label, variant, scale=1):
            prior = next((r for r in state['rounds'] if r['label'] == label), None)
            if prior:
                if prior['variant'] != variant or prior['latency_scale'] != scale:
                    raise ValueError('Frozen round configuration changed')
                return prior
            if len(state['rounds']) >= state['max_rounds']:
                raise RuntimeError('Bounded round budget exhausted')
            quota = read_limits(client.runner, root / 'runtime' / 'quota_request.json')
            require_headroom(quota, state['quota_stop_percent'])
            output = root / label
            record = {'label': label, 'variant': variant, 'output': str(output)}
            if record not in state['round_outputs']:
                state['round_outputs'].append(record)
            state.update(active_round=label, latest_quota=quota)
            save()
            while active_evaluators(output):
                time.sleep(2)
            status_path = output / 'status.json'
            if not status_path.exists():
                cmd = [sys.executable, str(source / 'evaluate_dev.py'), '--suite', str(args.suite),
                       '--profile', str(root / 'profile' / state['profile_name']),
                       '--output', str(output), '--variants', variant, '--screen-only',
                       '--episode-workers', '3', '--native-workers', '1',
                       '--quota-stop-percent', str(state['quota_stop_percent'])]
                if scale != 1:
                    cmd += ['--latency-scale', str(scale)]
                with (root / (label + '.log')).open('a') as log:
                    subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False)
            result = json.loads(status_path.read_text())
            if result['status'] != 'complete' or len(result['rounds']) != 1:
                raise RuntimeError(f'Incomplete round {label}; preserve results and stop: {result.get("error", result["status"])}')
            row = dict(result['rounds'][0], label=label)
            state['rounds'].append(row)
            save()
            return row

        champion = state['baseline']
        for index, axis in enumerate(AXES):
            candidate = round_(f'r{index + 1}_{axis}', add_axis(champion['variant'], axis))
            accepted = promote(candidate, champion)
            candidate['promoted'] = accepted
            candidate['compared_to'] = champion['variant']
            if accepted:
                champion = candidate
            state['best'] = champion
            save()
        repeat = round_('r4_confirmation', champion['variant'])
        state['confirmed_dev_target'] = champion['mean_score'] >= 1500 and repeat['mean_score'] >= 1500
        state['confirmation_mean'] = repeat['mean_score']
        if state['confirmed_dev_target']:
            stress = round_('r5_latency125', champion['variant'], 1.25)
            state['slower_delay_mean'] = stress['mean_score']
        state['status'] = 'complete'
        state['outcome'] = 'development_target_confirmed' if state['confirmed_dev_target'] else 'bounded_batch_complete_target_not_met'
        state.pop('active_round', None)
        save()
    except BaseException as exc:
        state['status'] = 'needs_attention'
        state['error'] = repr(exc)
        save()
        raise
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            lock.close()


if __name__ == '__main__':
    main()
