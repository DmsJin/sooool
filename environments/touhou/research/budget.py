"""Cross-process, persistent, fail-closed budget accounting (USD)."""
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import time
import uuid

D = lambda n: Decimal(str(n))
STAGE_CAPS = {"profile": D(6), "reprofile": D(3), "realtime": D(18)}

class BudgetError(RuntimeError):
    pass

class BudgetLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _transaction(self):
        with open(str(self.path) + ".lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.path.read_text()) if self.path.exists() else {"version": 1, "requests": {}, "blocked": None}
            # Abandoned reservations remain charged and stop future admission.
            for entry in state["requests"].values():
                if entry["status"] == "inflight" and not self._owner_alive(entry):
                    entry["status"] = "unknown"
                    state["blocked"] = "Abandoned inflight request; manual reconciliation required"
            try:
                yield state
            finally:
                tmp = self.path.with_name(self.path.name + ".tmp")
                with open(tmp, "w") as out:
                    out.write(json.dumps(state, separators=(",", ":")))
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tmp, self.path)
                fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)

    @staticmethod
    def _process_identity(pid):
        try:
            return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        except (OSError, IndexError):
            return None

    @classmethod
    def _owner_alive(cls, entry):
        pid = entry.get("owner_pid")
        return pid is not None and cls._process_identity(pid) == entry.get("owner_start") and entry.get("owner_start") is not None

    @staticmethod
    def _cost(entry):
        return D(entry["actual_usd"] if entry["status"] == "settled" else entry["reserved_usd"])

    def snapshot(self):
        with self._transaction() as state:
            result = json.loads(json.dumps(state))
            result["committed_usd"] = str(sum((self._cost(e) for e in state["requests"].values()), D(0)))
            return result

    def reserve(self, stage, worst_usd, metadata=None):
        amount = D(worst_usd)
        if stage not in STAGE_CAPS or not amount.is_finite() or amount <= 0:
            raise BudgetError("Invalid stage or reservation")
        with self._transaction() as state:
            if state["blocked"]:
                raise BudgetError("Ledger blocked: " + state["blocked"])
            entries = list(state["requests"].values())
            total = sum((self._cost(e) for e in entries), D(0))
            stage_total = sum((self._cost(e) for e in entries if e["stage"] == stage), D(0))
            if total + amount > D(27) or stage_total + amount > STAGE_CAPS[stage]:
                raise BudgetError("Budget admission cap exceeded")
            rid = uuid.uuid4().hex
            state["requests"][rid] = {"stage": stage, "status": "inflight", "reserved_usd": str(amount), "created_at": time.time(), "owner_pid": os.getpid(), "owner_start": self._process_identity(os.getpid()), "metadata": metadata or {}}
            return rid

    def settle(self, rid, actual_usd, usage=None):
        amount = D(actual_usd)
        if not amount.is_finite() or amount < 0:
            raise BudgetError("Invalid settlement")
        error = None
        with self._transaction() as state:
            entry = state["requests"][rid]
            if entry["status"] != "inflight":
                raise BudgetError("Request already settled or unknown")
            entry.update(status="settled", actual_usd=str(amount), usage=usage, settled_at=time.time())
            if amount > D(entry["reserved_usd"]):
                error = "Actual usage exceeded conservative reservation"
            total = sum((self._cost(e) for e in state["requests"].values()), D(0))
            if total > D(30):
                error = "Absolute USD 30 accounting limit exceeded"
            if error:
                state["blocked"] = error
        if error:
            raise BudgetError(error)

    def block(self, reason):
        """Stop admission without changing already-known billing records."""
        with self._transaction() as state:
            state['blocked'] = state['blocked'] or str(reason)

    def unknown(self, rid, reason):
        with self._transaction() as state:
            entry = state["requests"][rid]
            if entry["status"] == "inflight":
                entry.update(status="unknown", error=str(reason), settled_at=time.time())
            state["blocked"] = "Unknown usage; manual reconciliation required"


def reservation_usd(text, image_count, max_output_tokens):
    # One token per UTF-8 byte is conservative for text; images are bounded by
    # api_client to PNG <=640x480. No cache-hit savings assumed, allow cache writes.
    tokens = len(text.encode("utf-8")) + 512 + 8192 * image_count
    return D(tokens) * D(15) / D(1000000) + D(max_output_tokens) * D(60) / D(1000000)


def usage_usd(usage):
    inp, out = int(usage["input_tokens"]), int(usage["output_tokens"])
    details = usage.get("input_tokens_details") or {}
    cached = int(details.get("cached_tokens", 0))
    writes = int(details.get("cache_write_tokens", 0))
    if min(inp, out, cached, writes) < 0 or cached + writes > inp:
        raise BudgetError("Invalid token accounting")
    return (D(inp-cached-writes)*D(12) + D(cached)*D("0.6") + D(writes)*D(15) + D(out)*D(60)) / D(1000000)
