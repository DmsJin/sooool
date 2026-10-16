"""Causal action chunks and a process-safe, pessimistic paid-request ledger.

All times are game milliseconds. Answers enter submit only when they arrive.
The runner controls key release; this module emits instantaneous presses.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
import fcntl
import json
import math
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class ScheduledAction:
    lane: int
    game_ms: float
    request_id: str


class ActionScheduler:
    def __init__(self, executed_refractory_ms=160, commit_guard_ms=0):
        self.executed_refractory_ms = float(executed_refractory_ms)
        if not math.isfinite(self.executed_refractory_ms) or self.executed_refractory_ms < 0:
            raise ValueError('executed refractory period must be finite and nonnegative')
        self.commit_guard_ms = float(commit_guard_ms)
        if not math.isfinite(self.commit_guard_ms) or self.commit_guard_ms < 0:
            raise ValueError('commit guard must be finite and nonnegative')
        self.game_ms = float('-inf')
        self._chunks = []
        self._events = {}
        self._executed = set()
        self._last_executed = {}
        self._requests = set()
        self.rejected_late = 0
        self.rejected_stale = 0
        self.rejected_refractory = 0
        self.rejected_committed = 0

    def submit(self, request_id, observation_game_ms, actions, activation_ms,
               horizon_ms=None, lanes=None):
        """Add an arrived plan; horizon_ms is relative to its observation.

        lanes defines the chunk's authority (default: lanes in its actions).
        An empty corrective plan must explicitly supply lanes and horizon_ms.
        Freshness is (observation time, request_id), independent of arrival order.
        """
        if request_id in self._requests:
            raise ValueError('request_id already submitted')
        observation_game_ms, activation_ms = map(float, (observation_game_ms, activation_ms))
        if not all(map(math.isfinite, (observation_game_ms, activation_ms))):
            raise ValueError('timestamps must be finite')
        if activation_ms < observation_game_ms:
            raise ValueError('response cannot arrive before observation')
        parsed = []
        for lane, relative_ms in actions:
            if isinstance(lane, bool) or int(lane) != lane or not 0 <= lane < 4:
                raise ValueError('lane must be 0..3')
            relative_ms = float(relative_ms)
            if not math.isfinite(relative_ms) or relative_ms < 0:
                raise ValueError('action time must be finite and nonnegative')
            parsed.append((int(lane), observation_game_ms + relative_ms))
        covered = set(lanes if lanes is not None else (lane for lane, _ in parsed))
        if any(isinstance(lane, bool) or not isinstance(lane, int) or not 0 <= lane < 4 for lane in covered):
            raise ValueError('lanes must be integers 0..3')
        end = observation_game_ms + float(horizon_ms) if horizon_ms is not None else max((t for _, t in parsed), default=observation_game_ms)
        if not math.isfinite(end) or end < observation_game_ms:
            raise ValueError('invalid horizon')
        if any(lane not in covered or t > end for lane, t in parsed):
            raise ValueError('action outside chunk authority')
        freshness = (observation_game_ms, str(request_id))
        chunk = (freshness, covered, observation_game_ms, end)
        self._requests.add(request_id)
        self._chunks.append(chunk)
        now = max(self.game_ms, activation_ms)
        committed = [event for event, _ in self._events.values()
                     if self.commit_guard_ms > 0 and 0 <= event.game_ms - now <= self.commit_guard_ms]
        committed_keys = {(event.lane, event.game_ms) for event in committed}
        for key, (event, prior_freshness) in list(self._events.items()):
            if key not in committed_keys and event.lane in covered and observation_game_ms <= event.game_ms <= end and freshness > prior_freshness:
                del self._events[key]
        accepted = []
        for lane, when in parsed:
            key = (lane, when)
            if when < now or key in self._executed:
                self.rejected_late += 1
                continue
            if any(event.lane == lane and
                   (key == (event.lane, event.game_ms) or abs(when - event.game_ms) < self.executed_refractory_ms)
                   for event in committed):
                self.rejected_committed += 1
                continue
            last = self._last_executed.get(lane)
            if last is not None and 0 <= when - last < self.executed_refractory_ms:
                self.rejected_refractory += 1
                continue
            owner = max((f for f, ls, start, stop in self._chunks if lane in ls and start <= when <= stop), default=freshness)
            if owner > freshness:
                self.rejected_stale += 1
                continue
            event = ScheduledAction(lane, when, str(request_id))
            self._events[key] = (event, freshness)
            accepted.append(event)
        return accepted

    def pending(self):
        """Snapshot accepted future presses for replacing the browser queue."""
        return [event for event, _ in sorted(self._events.values(), key=lambda item: (item[0].game_ms, item[0].lane))]

    def acknowledge(self, lane, scheduled_game_ms, actual_game_ms, executed=True):
        """Consume a browser action log entry without emitting another press.

        Use this instead of advance() when the browser owns timed execution.
        Expired entries remove queue state but never start the refractory clock.
        Delayed/out-of-order delivery cannot rewind the clock or lane history.
        """
        if isinstance(lane, bool) or not isinstance(lane, int) or not 0 <= lane < 4:
            raise ValueError('lane must be 0..3')
        scheduled_game_ms, actual_game_ms = map(float, (scheduled_game_ms, actual_game_ms))
        if not all(map(math.isfinite, (scheduled_game_ms, actual_game_ms))):
            raise ValueError('timestamps must be finite')
        if type(executed) is not bool:
            raise ValueError('executed must be boolean')
        key = (lane, scheduled_game_ms)
        if key not in self._events:
            # JS seconds -> Python milliseconds may shift the final binary bit.
            # Match only an existing event, without rounding any scheduled time.
            candidates = [candidate for candidate in self._events
                          if candidate[0] == lane and abs(candidate[1] - scheduled_game_ms) <= 1e-6]
            if candidates:
                key = min(candidates, key=lambda candidate: (abs(candidate[1] - scheduled_game_ms), candidate[1]))
        self._events.pop(key, None)
        self.game_ms = max(self.game_ms, actual_game_ms)
        if executed:
            self._executed.add(key)
            self._last_executed[lane] = max(self._last_executed.get(lane, float('-inf')), actual_game_ms)

    def advance(self, game_ms):
        """Return presses due now; callers must advance on each game tick.

        Events passed between ticks execute on this tick (normal timer jitter).
        Plans that were already late when submitted never enter this queue.
        """
        game_ms = float(game_ms)
        if not math.isfinite(game_ms) or game_ms < self.game_ms:
            raise ValueError('game clock must be finite and monotonic')
        self.game_ms = game_ms
        result = []
        for key, (event, _) in sorted(self._events.items(), key=lambda item: (item[0][1], item[0][0])):
            if event.game_ms <= game_ms:
                last = self._last_executed.get(event.lane)
                if last is not None and 0 <= game_ms - last < self.executed_refractory_ms:
                    self.rejected_refractory += 1
                else:
                    result.append(event)
                    self._executed.add(key)
                    self._last_executed[event.lane] = game_ms
                del self._events[key]
        return result


MICRO = Decimal(1_000_000)


def usd_to_micros(usd):
    value = Decimal(str(usd))
    if not value.is_finite() or value < 0:
        raise ValueError('USD amount must be finite and nonnegative')
    return int((value * MICRO).to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True)
class TokenPricing:
    input_usd_per_million: str
    output_usd_per_million: str

    def cost_usd(self, input_tokens, output_tokens):
        if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in (input_tokens, output_tokens)):
            raise ValueError('token counts must be nonnegative integers')
        rates = [Decimal(str(self.input_usd_per_million)), Decimal(str(self.output_usd_per_million))]
        if any(not r.is_finite() or r < 0 for r in rates):
            raise ValueError('invalid token pricing')
        return (rates[0] * input_tokens + rates[1] * output_tokens) / MICRO


class BudgetExceeded(RuntimeError):
    pass


class BudgetLedger:
    """One shared ledger covers all phases, workers and retry request IDs.

    Reserve a conservative uncached input bound and enforced output token cap
    before transmitting a paid request. Unknown charges keep their reservation.
    A reservation is never silently released after an error or process crash.
    """
    def __init__(self, path, limit_usd='30'):
        self.path = Path(path)
        self.limit_micros = usd_to_micros(limit_usd)
        if self.limit_micros > 49_886_709:
            raise ValueError('authorized ceiling is USD 49.886709')
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def existing(cls, path):
        """Open the cumulative ledger with its explicit, validated ceiling."""
        path = Path(path)
        data = json.loads(path.read_text())
        limit = data['limit_micros']
        if type(limit) is not int or limit <= 0:
            raise ValueError('invalid persisted budget limit')
        ledger = cls(path, Decimal(limit) / MICRO)
        ledger.snapshot()
        return ledger

    @contextmanager
    def _locked(self, write=True):
        with open(str(self.path) + '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads(self.path.read_text()) if self.path.exists() else {'version': 1, 'limit_micros': self.limit_micros, 'requests': {}}
            if data['limit_micros'] != self.limit_micros:
                raise ValueError('ledger limit differs from configured limit')
            yield data
            if not write:
                return
            with tempfile.NamedTemporaryFile('w', dir=self.path.parent, delete=False) as handle:
                temporary = handle.name
                handle.write(json.dumps(data, sort_keys=True, separators=(',', ':')))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    @staticmethod
    def _committed(data):
        return sum(r['actual_micros'] if r['state'] == 'settled' else r['reserved_micros'] for r in data['requests'].values())

    def reserve(self, request_id, max_usd, phase):
        micros = usd_to_micros(max_usd)
        with self._locked() as data:
            if data.get('halted'):
                raise BudgetExceeded('paid submissions halted after underestimated reservation')
            if request_id in data['requests']:
                raise ValueError('request_id already reserved; retries need new IDs')
            if self._committed(data) + micros > self.limit_micros:
                raise BudgetExceeded('request would exceed USD budget including in-flight reservations')
            data['requests'][request_id] = {'state': 'reserved', 'reserved_micros': micros, 'phase': str(phase)}
        return micros

    def settle(self, request_id, actual_usd):
        actual = usd_to_micros(actual_usd)
        underestimated = False
        with self._locked() as data:
            record = data['requests'][request_id]
            if record['state'] == 'settled':
                if record['actual_micros'] != actual:
                    raise ValueError('settled usage cannot be changed')
                return
            underestimated = actual > record['reserved_micros']
            record.update(state='settled', actual_micros=actual)
            if underestimated:
                data['halted'] = True
        if underestimated:
            raise BudgetExceeded('actual charge exceeded reservation; recorded true spend, halt paid submissions')

    def mark_uncertain(self, request_id, reason):
        with self._locked() as data:
            record = data['requests'][request_id]
            if record['state'] != 'settled':
                record.update(state='uncertain', reason=str(reason))

    def snapshot(self):
        with self._locked(write=False) as data:
            committed = self._committed(data)
            return {'limit_micros': self.limit_micros, 'committed_micros': committed,
                    'remaining_micros': max(0, self.limit_micros - committed),
                    'requests': dict(data['requests'])}
