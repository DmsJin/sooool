"""Select affected registered environments and run their existing offline contracts."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime import envs
from runtime.run_support import serve


SHARED_TESTS = (
    "test_envs.py", "test_pingpong_cli.py", "test_evaluation_records.py",
    "test_realtime_cli.py", "test_discussion_redaction.py", "test_contracts.py",
    "test_gameplay_assets.py", "test_ci.py",
)
EXTRA_TESTS = {"asterix": ("test_api_failure_diagnostics.py",)}
# Existing shared modules: Touhou API/budget code and Badminton public observations.
CONSUMERS = {"touhou": ("asterix", "badminton"), "badminton": ("tabletennis",)}
# Rendering-dependent suites remain separate from installation and CPU contracts.
NATIVE_SKIP_REASONS = {
    "badminton": {"Requires pinned native badminton", "Requires the pinned GPU/native runtime"},
    "tabletennis": {"Requires pinned native table tennis and EGL"},
}


def select_environments(root, paths):
    """Map changed repository paths to registry entries, including shared requirements."""
    games = envs.load_registry(root)["games"]
    inputs = {name: {str(Path(p).relative_to(root)) for p in envs._install_inputs(root, game)}
              for name, game in games.items()}
    reasons = {name: [] for name in games}
    for path in paths:
        # Documentation does not change installation or executable task inputs.
        if path.endswith(".md") or path in ("LICENSE", ".gitignore"):
            continue
        owners = set()
        for name, game in games.items():
            prefixes = tuple(f"{directory}/{name}/" for directory in (
                "environments", "policies", "profiles", "assets", "artifacts"))
            test = f"tests/test_{name}"
            recipe = f"recipes/{name}"
            if (path in inputs[name] or path == game.get("runner") or path.startswith(prefixes)
                    or path == test + ".py" or path.startswith(test + "_")
                    or path == recipe + ".json" or path.startswith(recipe + "-")
                    or path.startswith(f"scripts/{name}_")
                    or Path(path).name in EXTRA_TESTS.get(name, ())):
                owners.add(name)
        # Shared code, registry changes, and unclassified executable inputs affect all games.
        pending = list(owners)
        for owner in pending:
            for consumer in CONSUMERS.get(owner, ()):
                if consumer in games and consumer not in owners:
                    owners.add(consumer)
                    pending.append(consumer)
        for name in owners or games:
            reasons[name].append(path)
    return {name: why for name, why in reasons.items() if why}


def changed_paths(root, base, head, *, pull_request=False):
    if pull_request:
        base = subprocess.check_output(["git", "merge-base", base, head], cwd=root, text=True).strip()
    # With rename detection disabled both the removed and added paths participate.
    data = subprocess.check_output(
        ["git", "diff", "--name-only", "--no-renames", "-z", base, head], cwd=root)
    return [path.decode() for path in data.split(b"\0") if path]


def select(args):
    registry = envs.load_registry(ROOT)
    if args.all:
        reasons = {name: ["explicit full check"] for name in registry["games"]}
    elif args.base:
        reasons = select_environments(ROOT, changed_paths(ROOT, args.base, args.head))
    else:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        event_name = os.environ["GITHUB_EVENT_NAME"]
        if event_name == "workflow_dispatch" or (event_name == "push" and set(event["before"]) == {"0"}):
            reasons = {name: ["full check"] for name in registry["games"]}
        elif event_name == "pull_request":
            pr = event["pull_request"]
            paths = changed_paths(ROOT, pr["base"]["sha"], pr["head"]["sha"], pull_request=True)
            reasons = select_environments(ROOT, paths)
        elif event_name == "push":
            reasons = select_environments(ROOT, changed_paths(ROOT, event["before"], event["after"]))
        else:
            raise ValueError(f"Unsupported CI event: {event_name}")
    matrix = {"include": [{"game": name, "python": registry["games"][name]["python"],
                           "browser": registry["games"][name].get("browser", False),
                           "setup": registry["games"][name].get("setup", "")}
                          for name in reasons]}
    print(json.dumps({"matrix": matrix, "reasons": reasons}, indent=2))
    if "GITHUB_OUTPUT" in os.environ:
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write(f"matrix={json.dumps(matrix)}\ncount={len(reasons)}\n")
    summary("Selected environments", [f"{name}: {', '.join(why)}" for name, why in reasons.items()]
            or ["Documentation only; shared tests run."])


def summary(title, lines):
    if "GITHUB_STEP_SUMMARY" in os.environ:
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
            output.write(f"### {title}\n\n" + "\n".join(f"- {line}" for line in lines) + "\n\n")


def suite(args):
    if args.game:
        sys.path.insert(0, str(ROOT / "environments" / args.game))
    if args.module:
        tests = unittest.defaultTestLoader.loadTestsFromName(args.module)
    else:
        tests = unittest.defaultTestLoader.discover(str(ROOT / args.start), pattern=args.pattern)
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    unexpected = [(str(test), why) for test, why in result.skipped
                  if why not in NATIVE_SKIP_REASONS.get(args.game, set())]
    summary(args.module or f"{args.start}/{args.pattern}", [
        f"Executed {result.testsRun - len(result.skipped)} tests; {len(result.skipped)} skipped.",
        *[f"Not covered: {test}: {why}" for test, why in result.skipped],
    ])
    if not result.wasSuccessful() or result.testsRun == 0 or unexpected:
        raise SystemExit(f"Suite failed, ran no tests, or had unexpected skips: {unexpected}")


def run_suite(python, start, pattern="test_*.py", *, game=None, module=None, environ=None):
    command = [str(python), str(ROOT / "scripts/ci.py"), "suite", "--start", start, "--pattern", pattern]
    if game:
        command.extend(["--game", game])
    if module:
        command.extend(["--module", module])
    directory = ROOT / "environments" / game if game and start.startswith(f"environments/{game}/") else ROOT
    subprocess.run(command, cwd=directory, env=environ, check=True)


def shared():
    # Only the shared-test command needs this CI dependency; select/gate use stdlib.
    from imageio_ffmpeg import get_ffmpeg_exe

    subprocess.run(["uv", "--version"], check=True)  # Missing uv must not skip installer contracts.
    subprocess.run([sys.executable, "-S", "-m", "runtime.cli", "env", "list"], cwd=ROOT, check=True)
    with tempfile.TemporaryDirectory() as directory:
        binary = get_ffmpeg_exe()
        (Path(directory) / "ffmpeg").symlink_to(binary)
        print(f"Media tests use {binary}", flush=True)
        environ = {**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"]}
        for pattern in SHARED_TESTS:
            run_suite(sys.executable, "tests", pattern, environ=environ)


def environment(name):
    game = envs.load_registry(ROOT)["games"][name]
    # Restrict optional private-source credentials to the installation subprocess.
    token = os.environ.pop("CI_SOURCE_READ_TOKEN", "")
    install_env = os.environ.copy()
    if token:
        authorization = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        install_env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                           GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {authorization}")
    subprocess.run([sys.executable, "-m", "runtime.cli", "env", "setup", name],
                   cwd=ROOT, env=install_env, check=True)
    state = envs.status(ROOT, name)
    python = state["python"]
    subprocess.run(["uv", "pip", "check", "--python", python], check=True)
    if "runner" not in game:
        summary(name, ["Registered setup and dependency checks passed.",
                       "No runner declared; gameplay is not covered."])
        return
    environ = envs._python_environment(python)
    if "source_variable" in game and name != "badminton":
        environ[game["source_variable"]] = state["source"]
    # GPU-dependent suites report explicit skips on ordinary CPU runners.
    environ.pop("BADMINTON_ENV_ROOT", None)
    environ.update(MUJOCO_GL="egl", LIBGL_ALWAYS_SOFTWARE="1", LP_NUM_THREADS="2")
    patterns = [f"test_{name}*.py", *EXTRA_TESTS.get(name, ())]
    if name == "tabletennis":
        patterns = [path.name for path in sorted((ROOT / "tests").glob("test_tabletennis*.py"))]
    if not patterns:
        raise RuntimeError(f"No offline suites found for {name}")

    def contracts():
        for pattern in patterns:
            suite_env = dict(environ)
            if pattern == "test_tabletennis_simulation_native.py":
                suite_env.pop("TABLETENNIS_ENV_ROOT", None)
            run_suite(python, "tests", pattern, game=name, environ=suite_env)
        if name == "touhou":
            run_suite(python, "environments/touhou/research/tests", game=name, environ=environ)
            directory = ROOT / "environments/touhou"
            subprocess.run(["node", "--test", "tests/engine.test.mjs"], cwd=directory, check=True)
            subprocess.run([python, "tests/check_gym.py"], cwd=directory, check=True)
        elif name == "rhythm":
            run_suite(python, "environments/rhythm/experiments/rhythm/tests", game=name, environ=environ)
        elif name in ("racing", "badminton"):
            for path in sorted((ROOT / "environments" / name).glob("test_*.py")):
                run_suite(python, "tests", game=name, module=f"environments.{name}.{path.stem}", environ=environ)

    if name == "touhou":
        with serve(ROOT / "environments/touhou/dist") as url:
            environ["TOUHOU_TEST_URL"] = url
            contracts()
    else:
        contracts()
    if name == "pcba":
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run([sys.executable, "-m", "runtime.cli", "realtime-smoke", name,
                            "--output", str(Path(directory) / "smoke")], cwd=ROOT, env=environ, check=True)


def gate(needs):
    if needs["select"]["result"] != "success" or needs["shared"]["result"] != "success":
        raise SystemExit("Selection or shared checks did not succeed")
    selected = json.loads(needs["select"]["outputs"]["matrix"])["include"]
    expected = "success" if selected else "skipped"
    if needs["environment"]["result"] != expected:
        raise SystemExit(f"Environment checks must be {expected}: {needs['environment']['result']}")
    summary("CI result", ["Shared tests passed.",
                          "Environment checks passed: " + (", ".join(row["game"] for row in selected) or "none selected")])
    print("All selected checks passed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    selection = commands.add_parser("select")
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--base")
    selection.add_argument("--head", default="HEAD")
    commands.add_parser("shared")
    check = commands.add_parser("environment")
    check.add_argument("game")
    tests = commands.add_parser("suite")
    tests.add_argument("--start", default="tests")
    tests.add_argument("--pattern", default="test_*.py")
    tests.add_argument("--module")
    tests.add_argument("--game")
    commands.add_parser("gate")
    args = parser.parse_args()
    if args.command == "select":
        select(args)
    elif args.command == "shared":
        shared()
    elif args.command == "environment":
        environment(args.game)
    elif args.command == "suite":
        suite(args)
    else:
        gate(json.loads(os.environ["CI_NEEDS"]))


if __name__ == "__main__":
    main()
