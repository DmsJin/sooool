"""Native 100 Hz single-seat table tennis with public cameras and reference commands."""
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(os.environ["TABLETENNIS_ENV_ROOT"]).expanduser().resolve()
sys.path.insert(0, str(ROOT))

from core import spec
from core.episode import load_plugin
from core.local import seat_spec
from core.observe import filter_fields
from core.sport import FINISHED, UNIT_OVER, MatchConfig


class TableTennisEnvironment:
    def __init__(self, level, seed):
        self.sport = load_plugin(ROOT / "sports/tabletennis/plugin.py")
        self.cfg = MatchConfig(sport="tabletennis", format="match-wallclock", seats=("A",),
                               seed=seed, level=level, action_level="high", play="program")
        self.allowed = spec.whitelist(spec.load(ROOT / "sports/tabletennis/plugin.py"))
        self.match = self.sport.build(self.cfg)
        self.layer = self.sport.action_layer("high")
        self.spec = seat_spec(self.sport, self.cfg, "A", m=self.match,
                              plugin=ROOT / "sports/tabletennis/plugin.py")
        # Contact deadlines are absolute native frames, independent of RPC latency.
        self.spec.pop("timing", None)
        self.frame = 0

    def state(self):
        state, leaked = filter_fields(self.match.observe("A"), self.allowed)
        if leaked:
            raise ValueError(f"Undeclared table tennis observation fields: {leaked}")
        return {**state, "seat": "A", "world": "running", "step": self.frame,
                "t_sim": self.frame / 100}

    def step(self):
        info = {}
        info["events"] = self.match.step()
        self.frame += 1
        phase = self.match.phase().state
        info["done"] = phase == FINISHED
        if phase == UNIT_OVER:
            self.match.resume()
            info["point_boundary"] = True
        return info

    def outcome(self):
        """Offline-only diagnostics; never included in actor snapshots."""
        final = self.match.final_fields()
        results = [{key: item.get(key) for key in ("kind", "returned", "hit", "summary")}
                   for item in final["results"]]
        serves = [{key: item.get(key) for key in ("point", "verdict", "code", "why")}
                  for item in final["our_serves"]]
        incoming = results
        return {"points_for": final["points_for"], "points_against": final["points_against"],
                "won": final["won"] if self.match.phase().state == FINISHED else None,
                "native_match_completed": self.match.phase().state == FINISHED,
                "serves": len(serves), "legal_serves": sum(item["verdict"] == "good" for item in serves),
                "incoming": len(incoming),
                "legal_returns": sum(bool(item["returned"] and item["hit"]) for item in incoming),
                "results": results, "serve_results": serves, "points": final["points"]}

    def close(self):
        self.match = None
