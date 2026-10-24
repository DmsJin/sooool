"""Declared executor: a model answer becomes a fixed key script, nothing else.

The actor returns one placement for the piece in play: ``{"piece": "S", "rot": 1, "col": 3, "reason": "..."}``.
The executor turns it into key presses computed ONLY from the answer and the published spawn rules:
rotate clockwise ``rot`` times (three turns are pressed as one counter-clockwise turn), move left or right until
the piece's left edge is at ``col``, hard drop. It never reads the board, the piece position or any other game
internals, so the same script works on a real screen. Edge-triggered keys are separated by one released frame.

Spawn detection is public too: a new piece is recognised when the NEXT box on the screen changes, or when the
executor itself pressed hard drop. A stale answer (for a piece that already locked) is discarded.
"""
from __future__ import annotations

import json
from typing import Any

from engine import CCW, CELLS, CW, HARD, LEFT, RIGHT, KINDS
from render import NEXT_BOX, SPAWN_BG, SPAWN_STRIP

SPAWN_X = {kind: (4 if kind == "O" else 3) for kind in KINDS}


def parse_answer(text: str) -> dict:
    """Extract the single JSON object from a public answer. Raises ValueError for anything unusable."""
    if not isinstance(text, str) or "{" not in text or "}" not in text:
        raise ValueError("no JSON object in answer")
    value = json.loads(text[text.index("{"):text.rindex("}") + 1])
    return _placement(value)


def parse_answers(text: str, count: int) -> list[dict]:
    """``count`` placements (piece in play first, then the NEXT piece) from a ``{"placements": [...]}`` answer."""
    if count == 1:
        return [parse_answer(text)]
    if not isinstance(text, str) or "{" not in text or "}" not in text:
        raise ValueError("no JSON object in answer")
    value = json.loads(text[text.index("{"):text.rindex("}") + 1])
    items = value.get("placements") if isinstance(value, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("placements list missing")
    reason = value.get("reason")
    out = [_placement(dict(item, reason=reason)) for item in items[:count]]
    return out


def _placement(value) -> dict:
    if not isinstance(value, dict):
        raise ValueError("answer is not a JSON object")
    piece = str(value.get("piece", "")).upper()[:1]
    if piece not in KINDS:
        raise ValueError("piece letter missing or unknown")
    rot, col = int(value["rot"]), int(value["col"])
    if not 0 <= rot <= 3 or not 0 <= col <= 9:
        raise ValueError("rot must be 0-3 and col 0-9")
    reason = value.get("reason")
    if reason is not None and (not isinstance(reason, str) or len(reason) > 400):
        raise ValueError("reason must be a short string")
    return {"piece": piece, "rot": rot, "col": col, "reason": reason}


def key_script(answer: dict[str, Any]) -> list[int]:
    """Keys for one placement, computed from the answer alone (see module docstring)."""
    piece, rot, col = answer["piece"], answer["rot"] % 4, answer["col"]
    rot = 0 if piece == "O" else rot
    left = SPAWN_X[piece] + min(c for _, c in CELLS[piece][rot])  # left edge after rotating at the spawn column
    keys = [CW] * rot if rot <= 2 else [CCW]
    dx = col - left
    keys += [RIGHT if dx > 0 else LEFT] * abs(dx)
    return keys + [HARD]


def next_box(frame) -> bytes:
    """Pixels of the NEXT preview box; a change means a new piece is in play."""
    x0, y0, x1, y1 = NEXT_BOX
    return frame[y0:y1, x0:x1].tobytes()


def spawn_strip_occupied(frame) -> bool:
    """True when anything is drawn in the spawn rows (a piece just appeared there)."""
    x0, y0, x1, y1 = SPAWN_STRIP
    return bool((frame[y0:y1, x0:x1] != SPAWN_BG).any())


class KeyExecutor:
    """Plays key scripts frame by frame with press/release edges. ``step(env, screen)`` returns the action."""

    def __init__(self):
        self.script: list[int] = []
        self.piece_index = 0          # public count of pieces seen (spawns detected on the screen)
        self._last_next: bytes | None = None
        self._strip_was_occupied = True
        self.dropped = False          # the executor pressed hard drop on the previous frame
        self.applied: list[dict] = []
        self.plans: dict[int, dict] = {}   # placements received ahead of time, by public piece index
        self.started_for = -1               # piece index whose key script has started
        self.hover = False                  # position pieces but hard-drop only once the next piece's plan is known

    def observe(self, screen) -> bool:
        """Update the public piece counter from the screen. Returns True when a new piece was detected."""
        box, occupied = next_box(screen), spawn_strip_occupied(screen)
        new = self._last_next is not None and (box != self._last_next or self.dropped
                                                or (occupied and not self._strip_was_occupied))
        self._last_next, self._strip_was_occupied, self.dropped = box, occupied, False
        if new:
            self.piece_index += 1
            self.script = []  # a script for a piece that is gone is never continued
            self._start_if_planned()
        return new

    def _start_if_planned(self):
        plan = self.plans.pop(self.piece_index, None)
        if plan is not None and not self.script:
            self.script, self.started_for = key_script(plan), self.piece_index
            if self.hover:
                self.script = self.script[:-1]  # rotate and move now; the hard drop waits for the successor's plan
            self.applied.append({"piece_index": self.piece_index, "status": "started_from_plan", "keys": list(self.script),
                                 **{k: plan[k] for k in ("piece", "rot", "col")}})

    def apply_many(self, answers: list, first_target: int, frame: int) -> list[str]:
        """Newest observation wins: later answers replace stored plans; a piece whose keys already started keeps them."""
        statuses = []
        for offset, answer in enumerate(answers):
            target = first_target + offset
            if target < self.piece_index:
                statuses.append("stale")
            elif target == self.piece_index and self.started_for == self.piece_index:
                statuses.append("late")  # this piece is already being placed by an earlier answer
            else:
                self.plans[target] = answer
                statuses.append("applied")
            self.applied.append({"frame": frame, "target": target, "piece_index": self.piece_index, "status": statuses[-1],
                                 **{k: answer[k] for k in ("piece", "rot", "col")}})
        self._start_if_planned()
        return statuses

    def apply(self, answer: dict, target: int, frame: int) -> str:
        if target != self.piece_index:
            self.applied.append({"frame": frame, "target": target, "piece_index": self.piece_index, "status": "stale"})
            return "stale"
        self.script, self.started_for = key_script(answer), self.piece_index
        self.applied.append({"frame": frame, "target": target, "piece_index": self.piece_index, "status": "applied",
                             "keys": list(self.script), **{k: answer[k] for k in ("piece", "rot", "col")}})
        return "applied"

    def action(self, prev_action: int) -> int:
        if not self.script:
            if self.hover and self.started_for == self.piece_index and (self.piece_index + 1) in self.plans:
                if prev_action == HARD:
                    return 0
                self.dropped = True
                return HARD  # declared rule: drop the positioned piece once the next piece's placement is known
            return 0
        key = self.script[0]
        if prev_action == key:
            return 0  # release frame so the next press is an edge
        self.script.pop(0)
        if key == HARD:
            self.dropped = True
        return key
