"""Prepare game sources and Python environments, then launch their existing runners."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


def load_registry(root: Path) -> dict:
    registry = json.loads((root / "environments/registry.json").read_text())
    for name, game in registry["games"].items():
        if game["kind"] not in ("local", "external"):
            raise RuntimeError(f"Unknown environment kind for {name}: {game['kind']}")
    return registry


def canonical_name(registry: dict, name: str) -> str:
    return registry["aliases"][name] if name in registry["aliases"] else name


def cache_root() -> Path:
    base = Path(os.environ["XDG_CACHE_HOME"]) if "XDG_CACHE_HOME" in os.environ else Path.home() / ".cache"
    return base.expanduser().resolve() / "sooool"


def _git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def _source_revision(source: Path) -> str:
    if Path(_git(source, "rev-parse", "--show-toplevel")).resolve() != source:
        raise RuntimeError(f"Source must be a Git checkout root: {source}")
    return _git(source, "rev-parse", "HEAD")


def _install_inputs(root: Path, game: dict) -> dict:
    """Retain installation inputs, including the existing nested requirements files."""
    inputs = {}

    def requirements(path: Path) -> None:
        path = path.resolve()
        text = path.read_text()
        inputs[str(path)] = text
        for line in text.splitlines():
            tokens = shlex.split(line, comments=True)
            if tokens and tokens[0] in ("-r", "--requirement"):
                included = (path.parent / tokens[1]).resolve()
                if str(included) not in inputs:
                    requirements(included)

    if "setup" in game:
        inputs[str(root / game["setup"])] = (root / game["setup"]).read_text()
    else:
        requirements(root / game["requirements"])
    # Local editable packages declare their installation metadata here.
    for name in game.get("install_metadata", []):
        inputs[str(root / name)] = (root / name).read_text()
    return inputs


def _definition(root: Path, registry: dict, game: dict) -> dict:
    definition = {"project": str(root), "game": game, "inputs": _install_inputs(root, game)}
    if game["kind"] == "external":
        definition["source"] = registry["sources"][game["source"]]
    return definition


def _state_path(name: str) -> Path:
    return cache_root() / "state" / f"{name}.json"


def status(root: Path, name: str) -> dict:
    registry = load_registry(root)
    name = canonical_name(registry, name)
    game = registry["games"][name]
    python = cache_root() / "venvs" / name / "bin/python"
    if game["kind"] == "local":
        source, revision = root, _source_revision(root)
    else:
        spec = registry["sources"][game["source"]]
        revision = spec["revision"]
        source = cache_root() / "sources" / game["source"] / revision
    row = {"game": name, "status": "unprepared", "python": str(python), "source": str(source), "revision": revision}
    state_path = _state_path(name)
    if not state_path.exists():
        return row
    state = json.loads(state_path.read_text())
    row.update(source=state["source"], revision=state["revision"])
    if state["definition"] != _definition(root, registry, game):
        row["status"] = "needs-setup"
        return row
    if not python.exists() or not Path(state["source"]).is_dir():
        return row
    if game["kind"] == "external":
        source = Path(state["source"])
        revision = _source_revision(source)
        dirty = bool(_git(source, "status", "--porcelain"))
        row.update(revision=revision, dirty=dirty, local_source=state["local_source"])
        if revision != state["revision"] or (dirty and not state["local_source"]):
            row["status"] = "needs-setup"
            return row
    else:
        row["revision"] = _source_revision(root)
    row["status"] = "ready"
    return row


def _prepare_source(registry: dict, game: dict) -> Path:
    spec = registry["sources"][game["source"]]
    source = cache_root() / "sources" / game["source"] / spec["revision"]
    if not source.exists():
        source.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "remote", "add", "origin", spec["repository"]], check=True)
    # Refuse to overwrite edits or a manually switched managed checkout.
    head = subprocess.run(["git", "-C", str(source), "rev-parse", "--verify", "--quiet", "HEAD"],
                          text=True, capture_output=True)
    if head.returncode == 0:
        if _source_revision(source) != spec["revision"] or _git(source, "status", "--porcelain"):
            raise RuntimeError(f"Managed source changed; preserve it and use --source for development: {source}")
    elif head.returncode == 1:
        subprocess.run(["git", "-C", str(source), "fetch", "--depth", "1", "origin", spec["revision"]], check=True)
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", "FETCH_HEAD"], check=True)
    else:
        head.check_returncode()
    return source


def setup(root: Path, name: str, source: Path | None = None) -> dict:
    root = root.resolve()
    registry = load_registry(root)
    name = canonical_name(registry, name)
    game = registry["games"][name]
    if source is not None and game["kind"] == "local":
        raise RuntimeError(f"{name} uses this project's local source; --source applies to external environments")
    definition = _definition(root, registry, game)
    state_path = _state_path(name)
    # A failed install must not leave an old ready marker for a partly changed venv.
    state_path.unlink(missing_ok=True)
    if game["kind"] == "local":
        source_path = root
    else:
        source_path = source.expanduser().resolve(strict=True) if source is not None else _prepare_source(registry, game)
    _source_revision(source_path)
    venv = cache_root() / "venvs" / name
    python = venv / "bin/python"
    if not python.exists():
        subprocess.run(["uv", "venv", "--python", game["python"], str(venv)], check=True)
    elif not subprocess.check_output([str(python), "--version"], text=True).strip().startswith(f"Python {game['python']}."):
        subprocess.run(["uv", "venv", "--clear", "--python", game["python"], str(venv)], check=True)
    if "setup" in game:
        subprocess.run(["bash", str(root / game["setup"]), str(source_path), str(venv)], cwd=root, check=True)
    else:
        subprocess.run(["uv", "pip", "install", "--python", str(python), "-r", str(root / game["requirements"])],
                       cwd=root, check=True)
    if game.get("browser", False):
        subprocess.run([str(python), "-m", "playwright", "install", "chromium"], check=True)
    state = {"definition": definition, "source": str(source_path), "revision": _source_revision(source_path),
             "local_source": source is not None}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_name(f".{name}-{os.getpid()}.json")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(state_path)
    return status(root, name)


def _python_environment(python: str) -> dict:
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(Path(python).parent.parent)
    env["PATH"] = str(Path(python).parent) + os.pathsep + env["PATH"]
    # A previous environment's Python paths must not override this game's packages.
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def _prepared_python(root: Path, name: str, game: dict) -> tuple[str, dict]:
    state = status(root, name)
    if state["status"] != "ready":
        raise RuntimeError(f"Environment {name} is {state['status']}; run: sol env setup {name}")
    python = state["python"]
    env = _python_environment(python)
    if "variables" in game:
        env.update(game["variables"])
    if "source_variable" in game:
        env[game["source_variable"]] = state["source"]
    return python, env


def _launch_spec(root: Path, name: str, args: list[str]) -> tuple[list[str], dict]:
    registry = load_registry(root)
    name = canonical_name(registry, name)
    game = registry["games"][name]
    if "runner" not in game or args[0] not in game["commands"]:
        raise RuntimeError(f"Environment {name} does not support {args[0]}")
    python, env = _prepared_python(root, name, game)
    return [python, str(root / game["runner"]), *args], env


def launch(root: Path, name: str, args: list[str]) -> None:
    """Replace the CLI process with the registered game's prepared runner."""
    command, env = _launch_spec(root, name, args)
    os.execve(command[0], command, env)


def run_script(root: Path, name: str, script: Path, args: list[str]) -> None:
    """Use a game's prepared interpreter for an existing standalone game tool."""
    registry = load_registry(root)
    name = canonical_name(registry, name)
    python, env = _prepared_python(root, name, registry["games"][name])
    if Path(sys.prefix).resolve() != Path(python).parent.parent.resolve():
        os.execve(python, [python, str(script), *args], env)


def check(root: Path, name: str, args: list[str]) -> dict:
    """Collect one doctor's JSON result in its game's prepared interpreter."""
    command, env = _launch_spec(root, name, ["doctor", *args])
    result = subprocess.run(command, env=env, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def main(root: Path, argv: list[str]) -> None:
    registry = load_registry(root)
    parser = argparse.ArgumentParser(prog="sol env")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Show registered games and preparation status")
    prepare = commands.add_parser("setup", help="Prepare one game's sources and Python environment")
    prepare.add_argument("game", choices=[*registry["games"], *registry["aliases"]])
    prepare.add_argument("--source", type=Path, help="Use an existing Git checkout without switching or resetting it")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            for name in registry["games"]:
                print(json.dumps(status(root, name)))
        else:
            print(json.dumps(setup(root, args.game, args.source), indent=2))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"sol env: {exc}\n")
