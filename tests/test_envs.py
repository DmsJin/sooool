"""Long-lived source, installation and process contracts owned by the environment manager.

Use local Git repositories and real virtual environments. No game or model calls.
"""
import json
import io
import os
from pathlib import Path
import shutil
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime import envs


@unittest.skipUnless(shutil.which("uv"), "uv is required for environment preparation")
class EnvironmentContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        (self.root / "environments").mkdir(parents=True)
        self.upstream = self.base / "upstream"
        subprocess.run(["git", "init", "--quiet", str(self.upstream)], check=True)
        (self.upstream / "game.txt").write_text("original\n")
        subprocess.run(["git", "-C", str(self.upstream), "add", "game.txt"], check=True)
        subprocess.run(["git", "-C", str(self.upstream), "-c", "user.name=Environment Test",
                        "-c", "user.email=test@example.invalid", "commit", "--quiet", "-m", "fixture"], check=True)
        self.revision = subprocess.check_output(["git", "-C", str(self.upstream), "rev-parse", "HEAD"], text=True).strip()
        (self.root / "requirements.txt").write_text("-r nested.txt\n")
        (self.root / "nested.txt").write_text("# No dependencies in the test runner.\n")
        (self.root / "runner.py").write_text(
            "import json, os, signal, sys\n"
            "print(json.dumps({'argv': sys.argv[1:], 'prefix': sys.prefix, 'cwd': os.getcwd(), "
            "'source': os.environ['GAME_SOURCE'], 'pythonpath': os.environ.get('PYTHONPATH')}), flush=True)\n"
            "if sys.argv[1] == 'wait': signal.pause()\n"
            "raise SystemExit(17)\n")
        game = {"kind": "external", "source": "engine", "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                "requirements": "requirements.txt", "runner": "runner.py", "commands": ["simulate", "wait"],
                "source_variable": "GAME_SOURCE"}
        self.registry = {"sources": {"engine": {"repository": str(self.upstream), "revision": self.revision}},
                         "aliases": {"alias": "first"}, "games": {"first": game, "second": dict(game)}}
        self.save_registry()
        self.environment = patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.base / "cache")})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def save_registry(self):
        (self.root / "environments/registry.json").write_text(json.dumps(self.registry))

    def test_invalid_environment_kind_fails_before_preparation(self):
        self.registry["games"]["first"]["kind"] = "externel"
        self.save_registry()
        with self.assertRaisesRegex(RuntimeError, "Unknown environment kind"):
            envs.setup(self.root, "first")
        self.assertFalse(envs.cache_root().exists())

    def test_sources_are_shared_venvs_are_separate_and_setup_is_repeatable(self):
        first = envs.setup(self.root, "alias")
        second = envs.setup(self.root, "second")
        repeated = envs.setup(self.root, "first")
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first["source"], second["source"])
        self.assertNotEqual(first["python"], second["python"])
        self.assertEqual(first["python"], repeated["python"])
        self.assertEqual(first["revision"], self.revision)
        source = Path(first["source"])
        (source / "game.txt").write_text("preserve managed edits\n")
        with self.assertRaisesRegex(RuntimeError, "Managed source changed"):
            envs.setup(self.root, "first")
        self.assertEqual((source / "game.txt").read_text(), "preserve managed edits\n")
        self.assertEqual(envs.status(self.root, "first")["status"], "unprepared")

    def test_local_checkout_edits_arguments_cwd_and_exit_status_are_preserved(self):
        (self.upstream / "game.txt").write_text("local edits\n")
        prepared = envs.setup(self.root, "first", self.upstream)
        self.assertTrue(prepared["local_source"])
        self.assertTrue(prepared["dirty"])
        cwd = self.base / "caller with spaces"
        cwd.mkdir()
        code = "from pathlib import Path; import sys; from runtime.envs import launch; launch(Path(sys.argv[1]), 'first', sys.argv[2:])"
        result = subprocess.run([sys.executable, "-c", code, str(self.root), "simulate", "--output", "relative output", "$literal"],
                                cwd=cwd, capture_output=True, text=True,
                                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
        self.assertEqual(result.returncode, 17, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["argv"], ["simulate", "--output", "relative output", "$literal"])
        self.assertEqual(output["prefix"], str(Path(prepared["python"]).parent.parent))
        self.assertEqual(output["cwd"], str(cwd))
        self.assertEqual(output["source"], str(self.upstream))
        self.assertIsNone(output["pythonpath"])
        self.assertEqual((self.upstream / "game.txt").read_text(), "local edits\n")
        process = subprocess.Popen([sys.executable, "-c", code, str(self.root), "wait"], cwd=cwd,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
        try:
            self.assertTrue(select.select([process.stdout], [], [], 10)[0])
            self.assertEqual(json.loads(process.stdout.readline())["argv"], ["wait"])
            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(timeout=5), -signal.SIGTERM)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()

    def test_changed_requirements_and_failed_install_cannot_launch_as_ready(self):
        envs.setup(self.root, "first")
        (self.root / "nested.txt").write_text("# Changed installation input.\n")
        self.assertEqual(envs.status(self.root, "first")["status"], "needs-setup")
        with self.assertRaisesRegex(RuntimeError, "sol env setup first"):
            envs.launch(self.root, "first", ["simulate"])
        (self.root / "nested.txt").write_text("./missing-package.whl\n")
        with self.assertRaises(subprocess.CalledProcessError):
            envs.setup(self.root, "first")
        self.assertEqual(envs.status(self.root, "first")["status"], "unprepared")

    def test_setup_script_receives_the_source_and_selected_venv(self):
        script = self.root / "setup.sh"
        script.write_text('set -eu\nprintf "%s\\n%s\\n" "$1" "$2" > "$2/setup-inputs"\n')
        game = self.registry["games"]["first"]
        del game["requirements"]
        game["setup"] = "setup.sh"
        self.save_registry()
        state = envs.setup(self.root, "first", self.upstream)
        venv = Path(state["python"]).parent.parent
        self.assertEqual((venv / "setup-inputs").read_text().splitlines(), [str(self.upstream), str(venv)])

    def test_local_sources_use_separate_game_venvs_and_track_install_metadata(self):
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        game = {"kind": "local", "python": version, "requirements": "requirements.txt",
                "install_metadata": ["pyproject.toml"], "runner": "runner.py",
                "commands": ["simulate"]}
        self.registry["games"] = {"one": game, "two": dict(game)}
        self.save_registry()
        (self.root / "pyproject.toml").write_text('[project]\nname = "local-fixture"\nversion = "0.0.0"\n')
        (self.root / "runner.py").write_text(
            "import json, os, sys\n"
            "print(json.dumps({'prefix': sys.prefix, 'cwd': os.getcwd(), 'args': sys.argv[1:]}))\n")
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Environment Test",
                        "-c", "user.email=test@example.invalid", "commit", "--quiet", "-m", "fixture"], check=True)
        first = envs.setup(self.root, "one")
        second = envs.setup(self.root, "two")
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first["source"], str(self.root))
        self.assertNotEqual(first["python"], second["python"])
        self.assertEqual(envs.setup(self.root, "one")["python"], first["python"])
        for invocation in ("launch(Path(sys.argv[1]), 'one', sys.argv[2:])",
                           "run_script(Path(sys.argv[1]), 'one', Path(sys.argv[1])/'runner.py', sys.argv[2:])"):
            code = "from pathlib import Path; import sys; from runtime.envs import launch, run_script; " + invocation
            result = subprocess.run([sys.executable, "-c", code, str(self.root), "simulate", "--output", "relative output"],
                                    cwd=self.base, capture_output=True, text=True,
                                    env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output['prefix'], str(Path(first['python']).parent.parent))
            self.assertEqual(output['cwd'], str(self.base))
            self.assertEqual(output['args'], ['simulate', '--output', 'relative output'])
        (self.root / "pyproject.toml").write_text('[project]\nname = "local-fixture"\nversion = "0.0.1"\n')
        self.assertEqual(envs.status(self.root, "one")["status"], "needs-setup")
        with self.assertRaisesRegex(RuntimeError, "sol env setup one"):
            envs.launch(self.root, "one", ["simulate"])
        with self.assertRaisesRegex(RuntimeError, "--source applies to external"):
            envs.setup(self.root, "one", self.upstream)

    def test_setup_only_environment_rejects_runner_commands(self):
        self.registry["games"]["first"].pop("runner")
        self.registry["games"]["first"].pop("commands")
        self.save_registry()
        with self.assertRaisesRegex(RuntimeError, "does not support simulate"):
            envs.launch(self.root, "first", ["simulate"])

    def test_setup_selection_uses_registry_and_restricts_source_to_one_external_game(self):
        # Long-lived CLI contract: explicit selection and all share one registry.
        for argv, expected in ((["setup", "alias", "first", "second"], ["first", "second"]),
                               (["setup", "all"], ["first", "second"])):
            with patch.object(envs, "setup", return_value={}) as prepare, patch("sys.stdout", new_callable=io.StringIO):
                envs.main(self.root, argv)
            self.assertEqual([call.args[1] for call in prepare.call_args_list], expected)
        for argv in (["setup", "all", "first"], ["setup", "all", "--source", str(self.upstream)],
                     ["setup", "first", "second", "--source", str(self.upstream)]):
            with patch.object(envs, "setup") as prepare, patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    envs.main(self.root, argv)
            prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
