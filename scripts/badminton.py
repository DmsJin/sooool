"""Run badminton tactical control with public cameras and declared simulation or realtime clocks."""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environments.badminton.runner import audit_episode, run_episode


def realtime(args, parser):
    # Keep native and paid-API dependencies out of the simulation launcher path.
    from environments.badminton.realtime import run_realtime
    recipe = json.loads((ROOT / "recipes/badminton-realtime.json").read_text())
    config = dict(recipe["args"])
    if args.seed is not None:
        config["seed"] = args.seed
    preflight = args.command == "preflight"
    if preflight:
        config["max_game_seconds"] = args.duration if args.duration is not None else 10
    elif args.duration is not None:
        parser.error("eval uses the native match endpoint; --duration is for preflight or simulation")
    budget = None
    key = None
    if not preflight:
        try:
            budget = Decimal(args.budget_usd)
        except (InvalidOperation, TypeError):
            parser.error("eval requires a finite positive --budget-usd")
        if not budget.is_finite() or budget <= 0:
            parser.error("eval requires a finite positive --budget-usd")
        if args.env_file is not None:
            for line in args.env_file.read_text().splitlines():
                if line.strip().startswith("OPENAI_API_KEY="):
                    values = shlex.split(line.strip().split("=", 1)[1], comments=True)
                    if len(values) != 1:
                        parser.error("Expected one OPENAI_API_KEY value in --env-file")
                    key = values[0]
                    break
            if key is None:
                parser.error("OPENAI_API_KEY is absent from --env-file")
        else:
            key = os.environ["OPENAI_API_KEY"]
        if not key:
            parser.error("OPENAI_API_KEY is empty")
    output = args.output.resolve()
    if output.exists():
        parser.error("Realtime output must be a new directory")
    config["stop_file"] = str(output.parent / "STOP")
    environment = Path(os.environ["BADMINTON_ENV_ROOT"]).resolve()
    revision = args.environment_revision
    if revision is None:
        revision = subprocess.run(["git", "-C", str(environment), "rev-parse", "HEAD"],
                                  check=True, capture_output=True, text=True).stdout.strip()
    if revision != recipe["environment_revision"]:
        parser.error("External badminton environment revision differs from the realtime recipe")
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=index,name,driver_version", "--format=csv,noheader"],
                         check=True, capture_output=True, text=True).stdout.splitlines()
    source_revision = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                    check=True, capture_output=True, text=True).stdout.strip()
    manifest = {"game": "badminton", "mode": "realtime_api_preflight" if preflight else "realtime_api",
                "recipe": recipe, "resolved_config": config, "repository_base_revision": source_revision,
                "environment_revision": revision, "renderer": "egl_gpu", "gpu_device": os.environ["MUJOCO_EGL_DEVICE_ID"],
                "environment_identity_source": "explicit_pinned_snapshot" if args.environment_revision else "git_checkout",
                "gpu_inventory": gpu, "host": platform.node(), "python": platform.python_version(),
                "budget_usd": None if budget is None else str(budget), "source_snapshot": "source_snapshot",
                "dependencies": {name: importlib.metadata.version(name) for name in ("mujoco", "numpy", "Pillow")}}
    try:
        result = run_realtime(config, recipe, json.loads((ROOT / recipe["profile"]).read_text()), output,
                              key=key, budget_usd=budget, preflight=preflight)
    finally:
        key = None
        if output.exists():
            (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            snapshot = output / "source_snapshot"
            for name in ("environments/badminton", "policies/badminton", "profiles/badminton", "recipes/badminton-realtime.json",
                         "runtime/cli.py", "scripts/badminton.py", "environments/touhou/research/budget.py"):
                destination = snapshot / name
                if (ROOT / name).is_dir():
                    shutil.copytree(ROOT / name, destination, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / name, destination)
    print(json.dumps(result, indent=2))
    return 0 if (result["complete"] or preflight and result["clock_valid"]) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["simulate", "eval", "preflight", "audit", "report"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", choices=["rules", "sol", "sol-frozen"])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--duration", type=int)
    parser.add_argument("--budget-usd")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--environment-revision", help="Revision of an explicitly pinned external source snapshot")
    parser.add_argument("--profile-info", choices=["show", "hide"])
    parser.add_argument("--episodes", nargs="+", type=Path)
    args = parser.parse_args(argv)
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be positive")
    os.environ["MUJOCO_GL"] = "egl"
    os.environ["PYOPENGL_PLATFORM"] = "egl"
    if args.command in {"eval", "preflight"}:
        return realtime(args, parser)
    if args.command == "simulate" and args.duration not in (None, 10, 60):
        parser.error("Simulation --duration must be 10 or 60 game seconds")
    recipe = json.loads((ROOT / "recipes/badminton.json").read_text())
    if recipe["subscription_service_tier"] != "default":
        parser.error("Badminton subscription simulation requires the default tier with Fast disabled")
    config = dict(recipe["args"])
    for name in ("source", "seed", "duration", "profile_info"):
        value = getattr(args, name)
        if value is not None:
            config[name] = value
    output = args.output.resolve()
    if args.command == "report":
        if not args.episodes:
            parser.error("report requires --episodes")
        if all("recipe" in json.loads((episode / "run.json").read_text()) for episode in args.episodes):
            from environments.badminton.realtime_report import report_realtime
            result = {str(episode): report_realtime(episode) for episode in args.episodes}
        else:
            from environments.badminton.report import report_round
            result = report_round(output, args.episodes)
    elif args.command == "audit":
        run = json.loads((output / "run.json").read_text())
        if "recipe" in run:
            from environments.badminton.realtime_report import audit_realtime
            result = audit_realtime(output)
        else:
            result = audit_episode(output)
        if not result["matched"]:
            print(json.dumps(result, indent=2))
            return 1
    else:
        if output.exists():
            parser.error("Simulation output must be a new directory")
        environment_root = Path(os.environ["BADMINTON_ENV_ROOT"]).expanduser().resolve()
        config.update(stop_file=str(output.parent / "STOP"), environment_root=str(environment_root),
                      subscription_service_tier=recipe["subscription_service_tier"])
        profile = json.loads((ROOT / recipe["profile"]).read_text())
        revision = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                  check=True, capture_output=True, text=True).stdout.strip()
        gpu_inventory = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,driver_version", "--format=csv,noheader"],
            check=True, capture_output=True, text=True).stdout.strip().splitlines()
        manifest = {"game": "badminton", "mode": "subscription_with_simulated_profile",
                    "recipe": recipe, "resolved_config": config, "repository_revision": revision,
                    "source_path": "environments/badminton", "environment_revision": recipe["environment_revision"],
                    "environment_root": str(environment_root), "renderer": "egl_gpu",
                    "gpu_device": os.environ.get("MUJOCO_EGL_DEVICE_ID"),
                    "host": platform.node(), "gpu_inventory": gpu_inventory,
                    "python": platform.python_version(), "subscription_service_tier": "default",
                    "fast_mode": False, "real_time_api_acceptance": False,
                    "dependencies": {name: importlib.metadata.version(name) for name in ("mujoco", "numpy", "Pillow")},
                    "paid_api_calls": 0}
        manifest["source_snapshot"] = "source_snapshot"
        manifest["repository_revision_is_base"] = True
        with tempfile.TemporaryDirectory(prefix="badminton-source-") as temp:
            for name in ("environments/badminton", "policies/badminton", "profiles/badminton",
                         "recipes/badminton.json", "runtime/subscription.py", "runtime/cli.py", "scripts/badminton.py"):
                destination = Path(temp) / name
                if (ROOT / name).is_dir():
                    shutil.copytree(ROOT / name, destination, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / name, destination)
            try:
                result = run_episode(config, config["source"], config["seed"], output, config["duration"] * 100,
                                     profile if config["source"] != "rules" else None,
                                     profile_info=config["profile_info"] == "show")
            finally:
                if output.is_dir():
                    shutil.copytree(temp, output / "source_snapshot")
                    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if result["status"] not in {"completed", "screen_completed"}:
            print(json.dumps(result, indent=2))
            return 1
    print(json.dumps({k: v for k, v in result.items() if k != "trajectory"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
