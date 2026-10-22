"""Argument and recording support shared by the three original experiment runners."""
import argparse
import os
from pathlib import Path
import time

from runtime.evaluation import recording
from runtime.run_support import ROOT, freeze
from runtime.options import positive_decimal, positive_float


def parser(game, *, profiling=False):
    """Build shared options only where the selected game supports them."""
    p = argparse.ArgumentParser(prog=f"sol <command> {game}")
    p.set_defaults(seed=None, duration=None, browser_executable=None, wall_seconds=None)
    commands = p.add_subparsers(dest="command", required=True)
    for command in ("simulate", "eval"):
        help_text = "Run the complete game" if game == "touhou" else None
        child = commands.add_parser(command, prog=f"sol {command} {game}", description=help_text)
        child.add_argument("--output", type=Path)
        if game != "rhythm" or command == "simulate":
            child.add_argument("--seed", type=int)
        if game != "touhou":
            child.add_argument("--duration", type=positive_float,
                               help="Game duration in seconds" + ("; must match the chart" if game == "rhythm" else ""))
        if game != "asterix":
            child.add_argument("--browser-executable")
        child.add_argument("--recipe", type=Path)
        providers = ["subscription"] if command == "simulate" else ["subscription", "api"] if game == "asterix" else ["api"]
        child.add_argument("--provider", choices=providers, default=providers[0],
                           help=f"Decision source (default: {providers[0]})")
        if command == "eval":
            child.add_argument("--budget-usd", type=positive_decimal,
                               help="Cumulative ledger ceiling in USD; required for paid API evaluation")
            child.add_argument("--max-calls", type=int, default=None if game == "asterix" else 100,
                               help="Paid API call limit (default: 100)")
            child.add_argument("--ledger", type=Path, help="Cumulative API budget ledger")
            if game == "rhythm":
                child.add_argument("--audio", type=Path)
            if game == "asterix":
                child.add_argument("--wall-seconds", type=positive_float, help="Wall-clock duration in seconds")
    if profiling:
        child = commands.add_parser("profile", prog=f"sol profile {game}", help="Serial API profiling of retained inputs")
        child.add_argument("--episode", type=Path, required=True)
        child.add_argument("--output", type=Path)
        child.add_argument("--budget-usd", type=positive_decimal, required=True, help="Cumulative ledger ceiling in USD")
        child.add_argument("--provider", choices=["api"], default="api")
        child.add_argument("--max-calls", type=int, default=21)
        child.add_argument("--ledger", type=Path, help="Cumulative API budget ledger")
    return p


def validate_budget(p, a):
    if a.budget_usd is None:
        p.error("--budget-usd is required for paid API evaluation")
    if a.max_calls < 1:
        p.error("--max-calls must be positive")


def execute(a, recipe, mode, action):
    """Retain the existing run, failure and evaluation records around a game callback."""
    out = (a.output or ROOT/'runs'/f'{a.game}-{time.strftime("%Y%m%dT%H%M%S")}').resolve()
    with recording(out, game=a.game, command=a.command, provider=a.provider,
                   clock='virtual' if a.command == 'simulate' else 'wall',
                   detail_file='record.json' if a.game == 'touhou' else None):
        freeze(a.game, recipe, out, mode=mode)
        (out/'transport').mkdir()
        os.environ['SOL_NATIVE_LOG_ROOT'] = str(out/'transport')
        result = action(recipe, out, a)
    return out, result
