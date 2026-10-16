"""Pure controller and atomic reservation rules for the paid realtime pilot."""
import json
import threading

from profile_policy_latency import usage_cost

VERTICAL = {1, 4, 5, 6, 7, 8}
RELEASE = {1: 0, 4: 0, 5: 2, 6: 3, 7: 2, 8: 3}


class BudgetStop(Exception):
    pass


class RealtimeBudget:
    def __init__(self, path, limit_micro_usd, prior_used=0):
        if not 0 < limit_micro_usd <= 20_000_000 or not 0 <= prior_used < limit_micro_usd:
            raise ValueError('Invalid or unauthorized budget')
        self.path = path
        self.limit = limit_micro_usd
        self.used = prior_used
        self.initial_used = prior_used
        self.pending = {}
        self.serial = 0
        self.stopped = False
        self.lock = threading.Lock()
        with path.open('x') as f:
            f.write(json.dumps({'event': 'start', 'limit_micro_usd': self.limit,
                                'prior_used_micro_usd': prior_used})+'\n')

    def _log(self, row):
        with self.path.open('a') as f:
            f.write(json.dumps(row)+'\n')

    def reserve(self, bound):
        with self.lock:
            if self.stopped or self.used+sum(self.pending.values())+bound > self.limit:
                self.stopped = True
                self._log({'event': 'blocked', 'bound': bound, 'used': self.used,
                           'pending': sum(self.pending.values())})
                raise BudgetStop('Total budget would be exceeded before dispatch')
            ticket = self.serial
            self.serial += 1
            self.pending[ticket] = bound
            self._log({'event': 'reserve', 'ticket': ticket, 'micro_usd': bound})
            return ticket

    def settle(self, ticket, usage, input_limit):
        with self.lock:
            bound = self.pending.pop(ticket)
            try:
                amount = usage_cost(usage)
                if usage['input_tokens'] > input_limit or usage['output_tokens'] > 256:
                    self.stopped = True
            except (KeyError, TypeError, ValueError):
                amount = bound
                self.stopped = True
            if amount > bound:
                self.stopped = True
            self.used += amount
            self._log({'event': 'settle', 'ticket': ticket, 'micro_usd': amount,
                       'uncertain': usage is None, 'stopped': self.stopped})
            return amount

    def snapshot(self):
        with self.lock:
            return {'accounted_usd': self.used/1e6,
                    'batch_accounted_usd': (self.used-self.initial_used)/1e6,
                    'pending_reserved_usd': sum(self.pending.values())/1e6,
                    'budget_stopped': self.stopped}


class HopController:
    def __init__(self):
        self.action = 0
        self.last = -1
        self.applied_at = None
        self.vertical_finished = -1
        self.applied = []

    def advance(self, frame, ready):
        if ready:
            row = max(ready, key=lambda r: r['seq'])
            if row['seq'] > self.last:
                self.action = row['chosen']
                suppressed = False
                if self.action in VERTICAL:
                    if row['obs_frame'] < self.vertical_finished:
                        self.action = RELEASE[self.action]
                        suppressed = True
                    else:
                        self.vertical_finished = frame+4
                self.last = row['seq']
                self.applied_at = frame
                event = {'frame': frame, 'seq': self.last, 'action': self.action,
                         'obs_frame': row['obs_frame'],
                         'capture_to_apply_s': row.get('capture_to_apply_s')}
                if suppressed:
                    event['reason'] = 'vertical_requires_fresh_observation'
                self.applied.append(event)
        if self.applied_at is not None and frame-self.applied_at >= 4 and self.action in VERTICAL:
            self.action = RELEASE[self.action]
            self.applied.append({'frame': frame, 'seq': self.last, 'action': self.action,
                                 'reason': 'vertical_timeout'})
        return self.action
