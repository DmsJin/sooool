"""Deliver legal streamed actions while retaining terminal/billing futures.

The caller executes actions. This helper never closes an early stream, releases a
reservation, retries a request, or selects a game action.
"""
import concurrent.futures as cf
import time


class ActionRequests:
    def __init__(self, pool, call, capacity, record_terminal):
        self.pool, self.call, self.capacity = pool, call, capacity
        self.record_terminal = record_terminal
        self.active = []

    @property
    def in_flight(self):
        # Ready actions still occupy capacity until their terminal is collected.
        return len(self.active)

    def submit(self, items, meta, choice_count=None, action_parser=None):
        if self.in_flight >= self.capacity:
            raise RuntimeError('Streaming request capacity reached')
        ready = cf.Future()

        def notify(row):
            if ready.done():
                raise RuntimeError('Duplicate streamed action notification')
            ready.set_result({**row, 'action_ready_received_wall': time.time()})

        def worker():
            try:
                kwargs = {'on_ready': notify, 'choice_count': choice_count}
                if action_parser is not None:
                    kwargs['action_parser'] = action_parser
                result = self.call(items, **kwargs)
                if not ready.done():
                    ready.set_exception(RuntimeError('Request ended without a legal streamed action'))
                return result
            except BaseException as exc:
                if not ready.done():
                    ready.set_exception(exc)
                raise

        submitted_at = time.perf_counter()
        request = {'ready': ready, 'completion': self.pool.submit(worker),
                   'meta': dict(meta), 'consumed': False, 'submitted_at': submitted_at}
        self.active.append(request)
        return request

    @staticmethod
    def checked(row):
        if row.get('error') or row.get('status') != 'completed':
            raise RuntimeError('Actual API request did not complete: ' + str(row.get('error')))
        return row

    def ready(self):
        for request in list(self.active):
            if request['consumed'] or not request['ready'].done():
                continue
            # If failure is already known, avoid delivering an otherwise ready action.
            if request['completion'].done():
                row = request['completion'].result()
                if row.get('error') or row.get('status') != 'completed':
                    self.collect()
            request['consumed'] = True
            yield request, request['ready'].result()

    def _finish(self, request, phase=None):
        self.active.remove(request)
        row = request['completion'].result()
        meta = dict(request['meta'])
        if phase is not None and not request['consumed']:
            meta['phase'] = phase
        self.record_terminal(row, meta)
        self.checked(row)
        return row

    def collect(self):
        errors = []
        for request in list(self.active):
            # Keep a finished successful response until its action is consumed;
            # otherwise collecting first could discard the unprocessed action.
            if not request['completion'].done():
                continue
            try:
                row = request['completion'].result()
                if not request['consumed'] and not row.get('error') and row.get('status') == 'completed':
                    continue
                self._finish(request)
            except BaseException as exc:
                if request in self.active:
                    self.active.remove(request)
                errors.append(exc)
        if errors:
            raise errors[0]

    def drain(self, phase):
        errors = []
        for request in list(self.active):
            try:
                # _finish waits through the terminal even when action was delivered.
                self._finish(request, phase)
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise errors[0]
