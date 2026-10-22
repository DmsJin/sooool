"""Long-lived CI selection and required-result contracts owned by scripts/ci.py."""
import copy
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.ci import ROOT, changed_paths, environment, gate, select_environments


class SelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "environments").mkdir()
        self.registry = {"aliases": {}, "sources": {}, "games": {
            "alpha": {"kind": "local", "python": "3.12", "requirements": "alpha.txt",
                      "runner": "scripts/alpha.py", "commands": ["simulate"]},
            "beta": {"kind": "local", "python": "3.11", "requirements": "beta.txt",
                     "runner": "scripts/beta.py", "commands": ["simulate"]},
        }}
        (self.root / "alpha.txt").write_text("-r common.txt\n")
        (self.root / "beta.txt").write_text("-r common.txt\n")
        (self.root / "common.txt").write_text("# shared fixture requirements\n")
        self.save_registry()

    def save_registry(self):
        (self.root / "environments/registry.json").write_text(json.dumps(self.registry))

    def test_task_paths_and_shared_requirements_select_their_consumers(self):
        for path in ("environments/alpha/engine.py", "scripts/alpha.py", "tests/test_alpha.py",
                     "policies/alpha/prompt.txt", "recipes/alpha-v2.json"):
            with self.subTest(path=path):
                self.assertEqual(set(select_environments(self.root, [path])), {"alpha"})
        self.assertEqual(set(select_environments(self.root, ["common.txt"])), {"alpha", "beta"})

    def test_shared_or_unknown_code_selects_all_and_documentation_selects_none(self):
        for path in ("runtime/envs.py", "environments/registry.json", "scripts/new-tool.py"):
            with self.subTest(path=path):
                self.assertEqual(set(select_environments(self.root, [path])), {"alpha", "beta"})
        self.assertEqual(select_environments(self.root, ["README.md", "docs/install.md"]), {})

    def test_new_registry_entry_participates_without_a_second_environment_list(self):
        self.registry["games"]["gamma"] = {**self.registry["games"]["alpha"], "runner": "scripts/gamma.py"}
        self.save_registry()
        self.assertEqual(set(select_environments(self.root, ["scripts/gamma.py"])), {"gamma"})
        self.assertEqual(set(select_environments(self.root, ["runtime/cli.py"])), {"alpha", "beta", "gamma"})

    def test_shared_game_modules_also_select_their_transitive_consumers(self):
        selected = select_environments(ROOT, ["environments/touhou/research/budget.py"])
        self.assertEqual(set(selected), {"touhou", "asterix", "badminton", "tabletennis"})
        selected = select_environments(ROOT, ["environments/badminton/public.py"])
        self.assertEqual(set(selected), {"badminton", "tabletennis"})

    def test_renames_include_old_and_new_paths(self):
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()
        git("init", "--quiet")
        old = self.root / "environments/alpha/old name.py"
        new = self.root / "environments/beta/new name.py"
        old.parent.mkdir()
        old.write_text("# fixture\n")
        git("add", ".")
        git("-c", "user.name=CI Test", "-c", "user.email=ci@example.invalid", "commit", "--quiet", "-m", "before")
        before = git("rev-parse", "HEAD")
        new.parent.mkdir()
        old.rename(new)
        git("add", "-A")
        git("-c", "user.name=CI Test", "-c", "user.email=ci@example.invalid", "commit", "--quiet", "-m", "after")
        paths = changed_paths(self.root, before, "HEAD", pull_request=True)
        self.assertEqual(set(paths), {"environments/alpha/old name.py", "environments/beta/new name.py"})
        self.assertEqual(set(select_environments(self.root, paths)), {"alpha", "beta"})


class ExecutionTests(unittest.TestCase):
    def test_private_source_credentials_are_confined_to_the_installer(self):
        def installer(*args, **kwargs):
            self.assertNotIn("CI_SOURCE_READ_TOKEN", os.environ)
            self.assertNotIn("CI_SOURCE_READ_TOKEN", kwargs["env"])
            header = kwargs["env"]["GIT_CONFIG_VALUE_0"].removeprefix("AUTHORIZATION: basic ")
            self.assertEqual(base64.b64decode(header).decode(), "x-access-token:fixture-read-token")
            self.assertEqual(kwargs["env"]["GIT_CONFIG_KEY_0"], "http.https://github.com/.extraheader")
            raise RuntimeError("stop at installation boundary")
        with patch.dict(os.environ, {"CI_SOURCE_READ_TOKEN": "fixture-read-token"}), \
                patch("scripts.ci.subprocess.run", side_effect=installer):
            with self.assertRaisesRegex(RuntimeError, "stop at installation boundary"):
                environment("asterix")

    def test_required_result_rejects_failed_cancelled_and_unexpectedly_skipped_jobs(self):
        needs = {"select": {"result": "success", "outputs": {"matrix": json.dumps({"include": [{"game": "alpha"}]})}},
                 "shared": {"result": "success"}, "environment": {"result": "success"}}
        gate(needs)
        for job, result in (("select", "failure"), ("shared", "failure"),
                            ("environment", "failure"), ("environment", "skipped"), ("environment", "cancelled")):
            with self.subTest(job=job, result=result):
                failed = copy.deepcopy(needs)
                failed[job]["result"] = result
                with self.assertRaises(SystemExit):
                    gate(failed)
        needs["select"]["outputs"]["matrix"] = json.dumps({"include": []})
        needs["environment"]["result"] = "skipped"
        gate(needs)

    def test_empty_suites_and_missing_prerequisites_cannot_pass(self):
        script = Path(__file__).resolve().parents[1] / "scripts/ci.py"
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, str(script), "suite", "--start", directory]
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            (Path(directory) / "test_fixture.py").write_text(
                "import unittest\n@unittest.skip('missing prerequisite')\n"
                "class Contract(unittest.TestCase):\n    def test_required(self): pass\n")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing prerequisite", result.stderr)
            with patch("scripts.ci.ROOT", Path(directory)), \
                    patch("scripts.ci.envs.load_registry", return_value={"games": {
                        "tabletennis": {"runner": "fixture.py", "source_variable": "TABLETENNIS_ENV_ROOT"}}}), \
                    patch("scripts.ci.envs.status", return_value={"python": sys.executable, "source": directory}), \
                    patch("scripts.ci.subprocess.run"):
                with self.assertRaisesRegex(RuntimeError, "No offline suites"):
                    environment("tabletennis")
