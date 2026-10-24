"""Offline Tetris contracts: engine determinism, key-only executor, public task text, rules runs and zero-model replay."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "environments/tetris")]

import baseline  # noqa: E402
import cli  # noqa: E402
import engine  # noqa: E402
import executor  # noqa: E402
import render  # noqa: E402
import runner  # noqa: E402
import task  # noqa: E402

RECIPE = json.loads((ROOT / "recipes/tetris.json").read_text())


def play(env, keys):
    for key in keys:
        env.step(key)
        env.step(engine.NOOP)


class Engine(unittest.TestCase):
    def test_same_seed_same_game(self):
        a, b = engine.Tetris(seed=7), engine.Tetris(seed=7)
        for _ in range(600):
            action = (a.tick // 7) % 8
            a.step(action)
            b.step(action)
        self.assertTrue((a.board == b.board).all())
        self.assertEqual((a.kind, a.lines, a.score, a.pieces), (b.kind, b.lines, b.score, b.pieces))

    def test_seven_bag(self):
        env = engine.Tetris(seed=3)
        kinds = [env.kind] + env.upcoming(13)
        self.assertEqual(sorted(kinds[:7]), sorted("IJLOSTZ"))
        self.assertEqual(sorted(kinds[7:14]), sorted("IJLOSTZ"))

    def test_gravity_speeds_up_with_level(self):
        self.assertGreater(engine.Tetris(start_level=1).frames_per_row(), engine.Tetris(start_level=5).frames_per_row())


class Executor(unittest.TestCase):
    def test_key_script_lands_every_legal_placement(self):
        """Keys computed from the answer alone reach the placement the answer names, on an empty board."""
        checked = 0
        for kind in "IJLOSTZ":
            for rot in range(1 if kind == "O" else 4):
                for col in range(10):
                    env = engine.Tetris(seed=0)
                    env.kind, env.rot, env.x, env.y = kind, 0, executor.SPAWN_X[kind], 0
                    expected = baseline.landing(env.board, kind, rot, col)
                    if expected is None:
                        continue
                    before = env.pieces
                    play(env, executor.key_script({"piece": kind, "rot": rot, "col": col}))
                    self.assertEqual(env.pieces, before + 1)
                    self.assertEqual(sorted(zip(*[list(x) for x in env.board.nonzero()])), sorted(expected), (kind, rot, col))
                    checked += 1
        self.assertGreater(checked, 150)

    def test_public_spawn_detection_matches_engine(self):
        env, ex = engine.Tetris(seed=5, start_level=9), executor.KeyExecutor()
        ex.observe(render.render(env))
        for frame in range(1500):  # mix of executor drops and natural locks under fast gravity
            if frame % 90 == 0 and not ex.script:
                ex.apply({"piece": env.kind, "rot": frame % 4, "col": (frame // 90) % 8}, ex.piece_index, frame)
            env.step(ex.action(env.prev_action))
            ex.observe(render.render(env))
            if env.over:
                break  # the terminal spawn overlaps the stack; nothing is controlled after it
            self.assertEqual(ex.piece_index, env.pieces, frame)
        self.assertGreater(env.pieces, 10)

    def test_stale_and_invalid_answers(self):
        ex = executor.KeyExecutor()
        self.assertEqual(ex.apply({"piece": "T", "rot": 0, "col": 3}, target=1, frame=0), "stale")
        for text in ("no json", '{"piece":"X","rot":0,"col":1}', '{"piece":"T","rot":4,"col":1}', '{"piece":"T","rot":0,"col":10}'):
            with self.assertRaises((ValueError, KeyError)):
                executor.parse_answer(text)
        parsed = executor.parse_answer('text {"piece":"t","rot":1,"col":2,"reason":"ok"} more')
        self.assertEqual((parsed["piece"], parsed["rot"], parsed["col"]), ("T", 1, 2))


class Task(unittest.TestCase):
    def test_selected_recipe_and_policy_hashes(self):
        meta = json.loads((ROOT / "policies/tetris/v8-keys/policy.json").read_text())
        self.assertEqual(RECIPE["policy"], "v8-keys")
        for key, name in (("prompt", "prompt_sha256"), ("system", "system_sha256"), ("output_instructions", "output_format_sha256")):
            self.assertEqual(hashlib.sha256((ROOT / RECIPE[key]).read_bytes()).hexdigest(), meta[name])
        self.assertEqual((RECIPE["args"]["requests_in_flight"], RECIPE["args"]["executor"]), (1, "key_script"))
        self.assertEqual(json.loads((ROOT / "recipes/tetris-1x.json").read_text())["args"]["slowdown"], 1)

    def test_task_text_states_mode_and_measured_delay(self):
        system, sim = task.build_task(ROOT, RECIPE, "simulation", ["piece #3: executed T rot1 col4"])
        _, live = task.build_task(ROOT, RECIPE, "realtime")
        self.assertIn("does not advance this simulated game", sim)
        self.assertIn("keeps advancing while you compute", live)
        self.assertIn("runs 2x slower", sim)
        self.assertIn("piece #3: executed T rot1 col4", sim)
        self.assertNotIn("{timing}", sim + live)
        self.assertIn("Do not use tools", system)
        median = sorted(task.profile_delays(ROOT, RECIPE))
        self.assertIn(f"{(median[len(median)//2] if len(median) % 2 else (median[len(median)//2-1]+median[len(median)//2])/2)/2:.1f} seconds", sim)

    def test_profile_rejects_bad_delays(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p.json"
            path.write_text(json.dumps({"capture_to_complete_seconds": [1.0, 0.0]}))
            with self.assertRaises(ValueError):
                task.profile_delays(Path(directory), {"profile": "p.json"})
        with self.assertRaises(ValueError):
            runner.delay_frames(1.0, 0.5)


class RulesRunAndReplay(unittest.TestCase):
    def test_rules_simulation_records_and_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            cli.main(["simulate", "--provider", "rules", "--seed", "4", "--level", "3", "--prefix", "15",
                      "--duration", "8", "--output", str(out)])
            record = json.loads((out / "evaluation-record.json").read_text())
            self.assertEqual((record["game"], record["provider"], record["clock"], record["status"]), ("tetris", "rules", "virtual", "completed"))
            summary = json.loads((out / "summary.json").read_text())
            episode = summary["episodes"][0]
            self.assertEqual(episode["case"], {"seed": 4, "level": 3, "prefix": 15})
            self.assertGreater(episode["calls"], 0)
            self.assertTrue((out / "manifest.json").exists() and (out / "source_snapshot/environments/tetris/runner.py").exists())
            (episode_dir,) = sorted(out.glob("episode-*"))
            rows = [json.loads(line) for line in (episode_dir / "requests.jsonl").read_text().splitlines()]
            self.assertTrue(all("image_sha256" in r for r in rows))
            result = runner.verify_replay(ROOT, RECIPE, episode_dir)
            self.assertEqual((result["model_calls"], result["verified_requests"]), (0, len(rows)))
            # A tampered answer must be caught by the replay check.
            rows[0]["answer"] = json.dumps({"piece": json.loads(rows[0]["answer"])["piece"], "rot": 0, "col": 0})
            (episode_dir / "requests.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            with self.assertRaises(AssertionError):
                runner.verify_replay(ROOT, RECIPE, episode_dir)

    def test_rules_baseline_never_sees_pixels_but_actors_never_see_truth(self):
        env = engine.Tetris(seed=1)
        answer, meta = baseline.RulesActor().act_on_truth(env)
        self.assertEqual(meta["auth"], "rules")
        self.assertEqual(executor.parse_answer(answer)["piece"], env.kind)
        source = (ROOT / "environments/tetris/runner.py").read_text()
        self.assertNotIn("env.board", source.split("def run_episode")[1].split("def episodes_from")[0].replace("board_state(env)", ""))


if __name__ == "__main__":
    unittest.main()
