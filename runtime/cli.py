"""Dispatch registered environment commands without importing game dependencies."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from runtime import envs

ROOT = Path(__file__).resolve().parents[1]


def main():
    argv = sys.argv[1:]
    if argv[:1] == ['env']:
        return envs.main(ROOT, argv[1:])
    registry = envs.load_registry(ROOT)
    if len(argv) > 1:
        name = envs.canonical_name(registry, argv[1])
        if name in registry['games'] and (
            argv[0] != 'record' or 'record' in registry['games'][name].get('commands', [])
        ):
            try:
                return envs.launch(ROOT, name, [argv[0], *argv[2:]])
            except (OSError, RuntimeError) as exc:
                raise SystemExit(str(exc)) from exc
    p = argparse.ArgumentParser(prog='sol')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('env', help='Prepare game sources and Python environments')
    d = sub.add_parser('doctor', help='Check each selected game in its prepared environment')
    d.add_argument('--game', choices=['all', 'rhythm', 'touhou', 'asterix'], default='all')
    d.add_argument('--auth', action='store_true')
    d.add_argument('--browser-executable')
    r = sub.add_parser('record', help='Append an immutable evaluation record')
    r.add_argument('--decision', choices=['retain', 'reject', 'diagnostic'])
    r.add_argument('--note')
    r.add_argument('run', type=Path)
    r.add_argument('--registry', type=Path, default=ROOT/'artifacts/touhou/evaluations.jsonl')
    commands = sorted({command for game in registry['games'].values() for command in game.get('commands', [])} - {'doctor', 'record'})
    for command in commands:
        c = sub.add_parser(command, help=f'{command} a registered game')
        c.add_argument('game', choices=[*registry['games'], *registry['aliases']])
    a = p.parse_args(argv)
    if a.command == 'doctor':
        browser_extra = ['--browser-executable', a.browser_executable] if a.browser_executable else []
        extra = (['--auth'] if a.auth else []) + browser_extra
        try:
            if a.game != 'all':
                return envs.launch(ROOT, a.game, ['doctor', *extra])
            results = {}
            failed = False
            for game in ('asterix', 'touhou', 'rhythm'):
                try:
                    results[game] = envs.check(ROOT, game, extra if game == 'asterix' else browser_extra)
                except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
                    results[game] = {'error': exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)}
                    failed = True
            print(json.dumps(results, indent=2))
            if failed:
                raise SystemExit(1)
            return
        except (OSError, RuntimeError) as exc:
            p.exit(1, f'sol doctor: {exc}\n')
    if a.command=='record':
        manifest=json.loads((a.run/'manifest.json').read_text())
        if manifest['game']=='rhythm':
            if a.decision is not None or a.note is not None:
                if a.decision is None or a.note is None:p.error('Supply both --decision and --note')
                from runtime.evaluation import assess
                print(json.dumps(assess(a.run,a.decision,a.note),indent=2))
            else:
                from runtime.rhythm import append_record
                registry=a.registry if a.registry!=ROOT/'artifacts/touhou/evaluations.jsonl' else ROOT/'artifacts/rhythm/evaluations.jsonl'
                print(json.dumps({'appended':append_record(a.run,registry),'registry':str(registry)}))
            return
        if manifest['game']=='asterix':
            if a.decision is None or a.note is None:p.error('Asterix assessments require --decision and --note')
            from runtime.evaluation import assess
            print(json.dumps(assess(a.run,a.decision,a.note),indent=2));return
        if a.decision is not None or a.note is not None:p.error('--decision and --note apply to Asterix/Rhythm assessments')
        from runtime.touhou_records import append_record
        print(json.dumps({'appended':append_record(a.run,a.registry),'registry':str(a.registry)}));return


if __name__ == '__main__':
    main()
