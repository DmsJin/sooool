"""Process-safe pessimistic accounting; no gameplay scheduling or policy."""
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
        self.path = Path(path).resolve()
        self.limit_micros = usd_to_micros(limit_usd)
        if self.limit_micros > 80_000_000:
            raise ValueError('authorized ceiling is USD 80')
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
