"""Run table tennis evaluation or subscription/API-profile development simulation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from runtime.evaluation import recording
from runtime.options import credential, positive_float


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.set_defaults(profile=None,delay_seed=None,ledger=None,budget_usd=None,stage_cap_usd=None)
    commands=parser.add_subparsers(dest="command",required=True)
    for command,providers in (("simulate",("subscription",)),("eval",("rules","subscription","api"))):
        child=commands.add_parser(command)
        child.add_argument("--output",type=Path,required=True)
        child.add_argument("--provider",choices=providers,default=providers[0],
                           help=f"Decision source (default: {providers[0]})")
        child.add_argument("--seed",type=int)
        child.add_argument("--duration",type=positive_float,help="Game duration in seconds")
        child.add_argument("--slowdown",type=positive_float)
        child.add_argument("--max-calls",type=int)
        child.add_argument("--model-workers",type=int,default=4)
        child.add_argument("--request-interval-s",type=positive_float,default=.65)
        child.add_argument("--rules-policy",choices=["safe_center","wide_left","wide_right","short_center"],default="safe_center")
        if command=="simulate":
            child.add_argument("--profile",type=Path)
            child.add_argument("--delay-seed",type=int)
        else:
            child.add_argument("--ledger",type=Path)
            child.add_argument("--budget-usd",type=positive_float,help="API cumulative ledger ceiling in USD (default: 20)")
            child.add_argument("--stage-cap-usd",type=positive_float,help="API realtime stage ceiling in USD (default: 3)")
    report=commands.add_parser("report")
    report.add_argument("--output",type=Path,required=True)
    args = parser.parse_args(argv)
    os.environ["MUJOCO_GL"] = "egl"
    os.environ["PYOPENGL_PLATFORM"] = "egl"
    if args.command == "report":
        from environments.tabletennis.replay import export_replay
        print(json.dumps(export_replay(args.output), indent=2))
        return 0
    if args.output.exists():
        parser.error("Output directory must be new")
    config = json.loads((ROOT / "recipes/tabletennis.json").read_text())
    args.source = "sol" if args.provider == "subscription" else args.provider
    for name in ("source", "seed", "duration", "slowdown", "max_calls", "model_workers", "request_interval_s", "rules_policy"):
        value = getattr(args, name)
        if value is not None:
            config[name] = value
    if config["duration"] <= 0 or config["slowdown"] <= 0 or config["max_calls"] < 0:
        parser.error("duration and slowdown must be positive; max-calls must be nonnegative")
    if config["model_workers"]<1 or config["request_interval_s"]<=0:
        parser.error("model-workers and request-interval-s must be positive")
    config.update(repository_revision=subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        repository_revision_is_base=True, source_path=str(ROOT),
        environment_root=str(Path(os.environ["TABLETENNIS_ENV_ROOT"]).resolve()),
        clock="subscription_with_simulated_api_profile" if args.command == "simulate" else "actual_wall_" + args.source,
        simulation=args.command == "simulate",
        native_planner="two-phase asynchronous native IK/trajectory + robot-only servo rehearsal",
        gpu_device=os.environ.get("MUJOCO_EGL_DEVICE_ID"), catch_up_steps=0,
        capture_stride=5, max_output_tokens=512, timeout_seconds=60)
    if args.command == "simulate":
        from environments.tabletennis.simulation import load_profile
        profile_path = (args.profile or ROOT / config["simulation_profile"]).resolve()
        profile = load_profile(profile_path)
        config.update(latency_profile=profile, latency_profile_path=str(profile_path),
                      delay_seed=args.delay_seed if args.delay_seed is not None else config["simulation_delay_seed"],
                      paid_api_calls=0, real_time_api_acceptance=False)
    key = None
    if args.source == "api":
        if args.ledger is None:
            parser.error("API runs require an explicit cumulative --ledger")
        config.update(api_budget_file=str(args.ledger.resolve()), api_limit_usd=20.0 if args.budget_usd is None else args.budget_usd,
                      budget_scope="tabletennis_realtime", budget_scope_limit_usd=3.0 if args.stage_cap_usd is None else args.stage_cap_usd,
                      service_tier="ultrafast")
        key = credential()
    elif args.ledger is not None or args.budget_usd is not None or args.stage_cap_usd is not None:
        parser.error("--ledger, --budget-usd and --stage-cap-usd require --provider api")
    from environments.tabletennis.runner import run_episode
    with recording(args.output, game="tabletennis", command=args.command, provider=args.provider,
                   clock="virtual" if args.command == "simulate" else "wall"):
        with tempfile.TemporaryDirectory(prefix="tabletennis-source-") as frozen:
            for name in ("environments/tabletennis", "environments/badminton/public.py",
                         "policies/tabletennis", "profiles/tabletennis", "recipes/tabletennis.json", "scripts/tabletennis.py",
                         "runtime/subscription.py", "runtime/api.py", "runtime/cli.py", "runtime/envs.py", "runtime/options.py", "runtime/evaluation.py", "environments/registry.json"):
                target = Path(frozen) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if (ROOT / name).is_dir():
                    shutil.copytree(ROOT / name, target, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copyfile(ROOT / name, target)
            try:
                result = run_episode(config, args.output, api_key=key)
            finally:
                if args.output.is_dir():
                    shutil.copytree(frozen, args.output / "source_snapshot")
    print(json.dumps(result, indent=2))
    return int(result["status"] == "failed")


if __name__ == "__main__":
    raise SystemExit(main())
