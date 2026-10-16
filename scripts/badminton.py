"""Run the frozen badminton tactical policy with public cameras and S2 clocks."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environments.badminton.runner import audit_episode, run_episode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["simulate", "audit", "report"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", choices=["rules", "sol", "sol-frozen"])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--duration", type=int, choices=[10, 60])
    parser.add_argument("--profile-info", choices=["show", "hide"])
    parser.add_argument("--episodes", nargs="+", type=Path)
    args = parser.parse_args(argv)
    os.environ["MUJOCO_GL"] = "egl"
    os.environ["PYOPENGL_PLATFORM"] = "egl"
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
        from environments.badminton.report import report_round
        result = report_round(output, args.episodes)
    elif args.command == "audit":
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
