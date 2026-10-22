"""Dispatch registered environment commands without importing game dependencies."""
import argparse
import json
from pathlib import Path
import sys

from runtime import envs
from runtime.evaluation import append_record, assess

ROOT = Path(__file__).resolve().parents[1]


def main():
    argv = sys.argv[1:]
    if argv[:1] == ['env']:
        return envs.main(ROOT, argv[1:])
    registry = envs.load_registry(ROOT)
    commands = sorted({command for game in registry['games'].values() for command in game.get('commands', [])})
    if len(argv) > 1 and argv[0] in commands:
        name = envs.canonical_name(registry, argv[1])
        if name in registry['games']:
            try:
                return envs.launch(ROOT, name, [argv[0], *argv[2:]])
            except (OSError, RuntimeError) as exc:
                raise SystemExit(str(exc)) from exc
    parser = argparse.ArgumentParser(prog='sol')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('env', help='Prepare game sources and Python environments')
    record = sub.add_parser('record', help='Register a run and optionally append a research decision')
    record.add_argument('run', type=Path)
    record.add_argument('--registry', type=Path)
    record.add_argument('--decision', choices=['retain', 'reject', 'diagnostic'])
    record.add_argument('--note')
    for command in commands:
        child = sub.add_parser(command, help=f'{command} a registered game')
        games = [name for name, game in registry['games'].items() if command in game.get('commands', [])]
        aliases = [alias for alias, name in registry['aliases'].items() if name in games]
        child.add_argument('game', choices=[*games, *aliases])
    args = parser.parse_args(argv)
    if args.command == 'record':
        if (args.decision is None) != (args.note is None):
            parser.error('Supply both --decision and --note')
        try:
            manifest = json.loads((args.run / 'manifest.json').read_text())
            game = manifest['game']
            if game not in registry['games']:
                parser.error(f'Unknown game in run manifest: {game}')
            destination = args.registry or ROOT / 'artifacts' / game / 'evaluations.jsonl'
            result = {'appended': append_record(args.run, destination), 'registry': str(destination)}
            if args.decision is not None:
                result['assessment'] = assess(args.run, args.decision, args.note)
            print(json.dumps(result, indent=2))
        except (OSError, ValueError) as exc:
            parser.exit(1, f'sol record: {exc}\n')


if __name__ == '__main__':
    main()
