"""Argument and recording support shared by the three original experiment runners."""
import argparse
from decimal import Decimal, InvalidOperation
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import time

from runtime.evaluation import record_run
from runtime.run_support import ROOT, freeze


def parser(game, *, profiling=False):
    """Build the existing experiment options for a game-owned command entrypoint."""
    p = argparse.ArgumentParser(prog=f"sol <command> {game}")
    commands = p.add_subparsers(dest="command", required=True)
    for command in ("simulate", "eval"):
        c = commands.add_parser(command, prog=f"sol {command} {game}")
        c.add_argument("--output", type=Path)
        c.add_argument("--seed", type=int)
        c.add_argument("--duration", type=float)
        c.add_argument("--browser-executable")
        c.add_argument("--recipe", type=Path)
        if command == "eval":
            c.add_argument("--budget-usd", help="Required for paid API evaluation")
            c.add_argument("--max-calls", type=int, default=100)
            c.add_argument("--ledger", type=Path)
            c.add_argument("--audio", type=Path)
            c.add_argument("--provider", choices=["subscription", "api"])
            c.add_argument("--wall-seconds", type=float)
    if profiling:
        c = commands.add_parser("profile", prog=f"sol profile {game}", help="Serial API profiling of retained inputs")
        c.add_argument("--episode", type=Path, required=True)
        c.add_argument("--output", type=Path)
        c.add_argument("--budget-usd", required=True)
        c.add_argument("--max-calls", type=int, default=21)
        c.add_argument("--ledger", type=Path)
    d = commands.add_parser("doctor", prog=f"sol doctor --game {game}")
    d.add_argument("--auth", action="store_true")
    d.add_argument("--browser-executable")
    return p


def validate_budget(p, a):
    if a.budget_usd is None:
        p.error("--budget-usd is required for paid API evaluation")
    try:
        a.budget_usd = Decimal(a.budget_usd)
    except InvalidOperation:
        p.error("--budget-usd must be a finite positive decimal")
    if not a.budget_usd.is_finite() or a.budget_usd <= 0 or a.max_calls < 1:
        p.error("Budget and max-calls must be positive")


def execute(a, recipe, mode, action):
    """Retain the existing run, failure and evaluation records around a game callback."""
    out = (a.output or ROOT/'runs'/f'{a.game}-{time.strftime("%Y%m%dT%H%M%S")}').resolve()
    freeze(a.game, recipe, out, mode=mode)
    (out/'transport').mkdir()
    os.environ['SOL_NATIVE_LOG_ROOT'] = str(out/'transport')
    try:
        result = action(recipe, out, a)
    except BaseException as exc:
        (out/'failure.json').write_text(json.dumps({'type': type(exc).__name__, 'message': str(exc)}, indent=2))
        raise
    finally:
        record_run(out)
    return out, result


def doctor(a):
    # Game dependencies must load only after dispatch into the game's interpreter.
    checks = {'python': sys.version.split()[0], 'node': bool(shutil.which('node')),
              'codex': os.environ.get('SOL_CODEX_BIN') or shutil.which('codex')}
    packages = ('ale-py', 'gymnasium', 'Pillow') if a.game == 'asterix' else ('playwright', 'gymnasium', 'Pillow')
    for name in packages:
        checks[name] = importlib.metadata.version(name)
    if a.game == 'asterix':
        from environments.asterix.simulate_5x import make_env
        env, obs, info, noops = make_env(2)
        try:
            checks['asterix_reset'] = {'shape': list(obs.shape), 'lives': info.get('lives')}
        finally:
            env.close()
    else:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=a.browser_executable)
            try:
                checks['chromium'] = browser.version
            finally:
                browser.close()
    if a.auth:
        from runtime.subscription import SubscriptionClient
        client = SubscriptionClient(output=ROOT/'runs'/f'doctor-auth-{a.game}')
        try:
            checks['auth'] = 'chatgpt'
            checks['quota'] = client.quota()
        finally:
            client.close()
    print(json.dumps(checks, indent=2))
