"""Expose the pinned native badminton match through its public player view."""
from __future__ import annotations

import base64
from dataclasses import dataclass, replace
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(os.environ["BADMINTON_ENV_ROOT"]).expanduser().resolve()
sys.path.insert(0, str(ROOT))

from core import spec
from core.episode import load_plugin
from core.local import seat_spec
from core.observe import filter_fields
from core.outcome import decide
from core.sport import FINISHED, UNIT_OVER, MatchConfig, Refused, parse_action


@dataclass
class Action:
    """Carry one native command or an explicit physics-only step."""

    value: object
    name: str
    is_noop: bool = False


_sport = None


def load_sport():
    """Load the badminton plugin once because native modules use global names."""
    global _sport
    if _sport is None:
        _sport = load_plugin(ROOT / "sports/badminton/plugin.py")
    return _sport


class BadmintonEnvironment:
    """Advance native 100 Hz physics and filter observations for seat A."""

    frame_ms = 10.0

    def __init__(self, *, level, seed, max_env_steps):
        self.sport = load_sport()
        self.plugin_path = ROOT / "sports/badminton/plugin.py"
        self.max_env_steps = max_env_steps
        self._cfg = MatchConfig(sport="badminton", format="match-wallclock", seats=("A",),
                                seed=seed, level=level, action_level="high", play="program")
        self._allowed = spec.whitelist(spec.load(self.plugin_path))
        self._renderer = self._observation = self.match = None
        self.env_step = 0

    def reset(self, seed=None):
        self.close()
        if seed is not None:
            self._cfg = replace(self._cfg, seed=seed)
        self.match = self.sport.build(self._cfg)
        self._layer = self.sport.action_layer(self._cfg.action_level)
        # The virtual scheduler, rather than the HTTP planner, owns reaction delay.
        self._layer.lead = 0
        if self.match.dt != .01:
            raise ValueError("Badminton requires the native 10 ms control step")
        self.env_step = 0
        self._spec = seat_spec(self.sport, self._cfg, "A", m=self.match, plugin=self.plugin_path)
        self._spec["timing"] = {"reaction_delay_steps": 0}
        self._spec["act"].update(lead_steps=0, lead_game_s=0.0,
            rule="The command takes effect when the latency-bench scheduler releases it; t starts at that step.")
        self._spec["skill_contract"]["act"]["notes"]["timing"] = self._spec["act"]["rule"]
        return self.observe()

    def public_state(self):
        """Return the same declared state for online observation and offline audit."""
        state, leaked = filter_fields(self.match.observe("A"), self._allowed)
        if leaked:
            raise ValueError(f"Undeclared native observation fields: {leaked}")
        return {**state, "seat": "A", "world": "running", "step": self.env_step,
                "t_sim": self.env_step * self.frame_ms / 1000,
                "done": self.match.phase().state == FINISHED}

    def observe(self):
        if self._observation is None:
            state = self.public_state()
            if self._renderer is None:
                self._renderer = self.sport.worker_init("render", "A", self._cfg)
            job, camera_metadata = self.match.camera_job("A")
            image = self.sport.worker_call(self._renderer, "render", job)["png"]
            self._observation = SimpleNamespace(
                data={"state": state, "observation": {
                    "image_png_b64": base64.b64encode(image).decode(), **camera_metadata}},
                env_step=self.env_step,
                metadata={"spec": self._spec})
        return self._observation

    def step(self, action):
        before = self.match.scores()
        info = {"applied_action": action.value, "applied_action_name": action.name}
        if not action.is_noop:
            try:
                cmd = parse_action(self._layer, "A", action.value, self.match, {})
                job = self._layer.snapshot("A", cmd, self.match, self.env_step)
                prepared = self._layer.prepare(job) if job is not None else None
                low, planning = self._layer.lower("A", cmd, prepared, self.match)
                applied = self.match.apply("A", low)
                info["action_result"] = {**planning, **applied}
                if "rejected" in applied:
                    info.update(invalid_action=True, action_error=applied["rejected"])
            except Refused as exc:
                info.update(invalid_action=True, action_error=str(exc))
        info["events"] = self.match.step()
        self.env_step += 1
        self._observation = None
        after = self.match.scores()
        reward = (after["A"] - before["A"]) - (after["opponent"] - before["opponent"])
        phase = self.match.phase().state
        done = phase == FINISHED
        winner = decide(self.match, sides=("A", "opponent")).winner if done else None
        truncated = not done and self.env_step >= self.max_env_steps
        if phase == UNIT_OVER and not truncated:
            self.match.resume()
            info["soft_reset"] = True
        info.update(task_metrics={"points_for": after["A"], "points_against": after["opponent"],
                                  "match_finished": done, "truncated": truncated, "success": winner == "A"})
        if done:
            info["winner"] = winner
        return SimpleNamespace(reward=float(reward), done=done, truncated=truncated, info=info)

    def close(self):
        if self._renderer is not None:
            self._renderer.r.close()
            self._renderer = None
        self.match = self._observation = None
