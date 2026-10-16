"""Merge sparse visual detections without cancelling unmentioned planned hits."""
import math

from .scheduler import ActionScheduler, ScheduledAction


class SparseActionScheduler(ActionScheduler):
    def __init__(self, executed_refractory_ms=160, commit_guard_ms=50, match_window_ms=100):
        super().__init__(executed_refractory_ms, commit_guard_ms)
        self.match_window_ms = float(match_window_ms)
        if not math.isfinite(self.match_window_ms) or self.match_window_ms < 0:
            raise ValueError('match window must be finite and nonnegative')

    def submit(self, request_id, observation_game_ms, actions, activation_ms,
               horizon_ms=None, lanes=None):
        if request_id in self._requests:
            raise ValueError('request_id already submitted')
        observation_game_ms, activation_ms = map(float, (observation_game_ms, activation_ms))
        if not all(map(math.isfinite, (observation_game_ms, activation_ms))) or activation_ms < observation_game_ms:
            raise ValueError('invalid observation/arrival timestamps')
        parsed = []
        for lane, relative_ms in actions:
            if isinstance(lane, bool) or not isinstance(lane, int) or not 0 <= lane < 4:
                raise ValueError('lane must be 0..3')
            relative_ms = float(relative_ms)
            if not math.isfinite(relative_ms) or relative_ms < 0:
                raise ValueError('action time must be finite and nonnegative')
            parsed.append((lane, observation_game_ms + relative_ms))
        covered = set(lanes if lanes is not None else (lane for lane, _ in parsed))
        if any(isinstance(lane, bool) or not isinstance(lane, int) or not 0 <= lane < 4 for lane in covered):
            raise ValueError('lanes must be 0..3')
        end = observation_game_ms + float(horizon_ms) if horizon_ms is not None else max((t for _, t in parsed), default=observation_game_ms)
        if not math.isfinite(end) or end < observation_game_ms or any(lane not in covered or when > end for lane, when in parsed):
            raise ValueError('action outside supplied horizon or lanes')
        self._requests.add(request_id)
        now = max(self.game_ms, activation_ms)
        freshness = (observation_game_ms, str(request_id))
        accepted = []
        for lane, when in parsed:
            key = (lane, when)
            if when < now or key in self._executed:
                self.rejected_late += 1
                continue
            last = self._last_executed.get(lane)
            if last is not None and 0 <= when - last < self.executed_refractory_ms:
                self.rejected_refractory += 1
                continue
            matches = [(old_key, event, prior) for old_key, (event, prior) in self._events.items()
                       if event.lane == lane and abs(event.game_ms - when) <= self.match_window_ms]
            if matches:
                old_key, event, prior = min(matches, key=lambda match: (abs(match[1].game_ms - when), match[1].game_ms))
                if freshness < prior:
                    self.rejected_stale += 1
                    continue
                if self.commit_guard_ms > 0 and 0 <= event.game_ms - now <= self.commit_guard_ms:
                    self.rejected_committed += 1
                    continue
                del self._events[old_key]
            event = ScheduledAction(lane, when, str(request_id))
            self._events[key] = (event, freshness)
            accepted.append(event)
        return accepted
