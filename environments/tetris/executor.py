"""Declared executor: a model answer becomes a fixed key script, nothing else.

The actor returns one placement for the piece in play: ``{"piece": "S", "rot": 1, "col": 3, "reason": "..."}``.
The executor turns it into key presses computed ONLY from the answer and the published spawn rules:
rotate clockwise ``rot`` times (three turns are pressed as one counter-clockwise turn), move left or right until
the piece's left edge is at ``col``, hard drop. It never reads the board, the piece position or any other game
internals, so the same script works on a real screen. Edge-triggered keys are separated by one released frame.

Spawn detection is public too: a new piece is recognised when the NEXT box on the screen changes, when the spawn
rows go from empty to occupied, or when the executor itself pressed hard drop. An answer for a piece that already
locked is discarded (``stale``), the placement analogue of Asterix discarding older replies.
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
    """Plays key scripts frame by frame with press/release edges. ``action(prev)`` returns this frame's key."""

    def __init__(self):
        self.script: list[int] = []
        self.piece_index = 0          # public count of pieces seen (spawns detected on the screen)
        self._last_next: bytes | None = None
        self._strip_was_occupied = True
        self.dropped = False          # the executor pressed hard drop on the previous frame
        self.applied: list[dict] = []

    @property
    def busy(self) -> bool:
        """True while a key script is still being pressed (the executor's own state, nothing read from the game)."""
        return bool(self.script)

    def observe(self, screen) -> bool:
        """Update the public piece counter from the screen. Returns True when a new piece was detected."""
        box, occupied = next_box(screen), spawn_strip_occupied(screen)
        new = self._last_next is not None and (box != self._last_next or self.dropped
                                                or (occupied and not self._strip_was_occupied))
        self._last_next, self._strip_was_occupied, self.dropped = box, occupied, False
        if new:
            self.piece_index += 1
            self.script = []  # a script for a piece that is gone is never continued
        return new

    def apply(self, answer: dict, target: int, frame: int) -> str:
        if target != self.piece_index:
            self.applied.append({"frame": frame, "target": target, "piece_index": self.piece_index, "status": "stale"})
            return "stale"
        self.script = key_script(answer)
        self.applied.append({"frame": frame, "target": target, "piece_index": self.piece_index, "status": "applied",
                             "keys": list(self.script), **{k: answer[k] for k in ("piece", "rot", "col")}})
        return "applied"

    def action(self, prev_action: int) -> int:
        if not self.script:
            return 0
        key = self.script[0]
        if prev_action == key:
            return 0  # release frame so the next press is an edge
        self.script.pop(0)
        if key == HARD:
            self.dropped = True
        return key
