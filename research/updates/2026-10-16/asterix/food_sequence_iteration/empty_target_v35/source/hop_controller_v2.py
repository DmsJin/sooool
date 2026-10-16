"""Finish an active four-frame hop when stale vertical replies are suppressed."""
VERTICAL = {1, 4, 5, 6, 7, 8}
RELEASE = {1: 0, 4: 0, 5: 2, 6: 3, 7: 2, 8: 3}
UP = {1, 5, 6}


class HopControllerV2:
    def __init__(self):
        self.action = 0
        self.last = -1
        self.vertical_finished = -1
        self.applied = []

    def advance(self, frame, ready):
        # Expire at the original deadline, irrespective of intervening replies.
        if self.action in VERTICAL and frame >= self.vertical_finished:
            self.action = RELEASE[self.action]
            self.applied.append({'frame': frame, 'seq': self.last,
                                 'action': self.action, 'reason': 'vertical_timeout'})
        if ready:
            row = max(ready, key=lambda r: r['seq'])
            if row['seq'] > self.last:
                chosen = row['chosen']
                if type(chosen) is not int or not 0 <= chosen <= 8:
                    raise ValueError('Invalid integer action')
                suppressed = chosen in VERTICAL and row['obs_frame'] < self.vertical_finished
                if suppressed:
                    horizontal = RELEASE[chosen]
                    if self.action in VERTICAL:
                        # A stale request cannot restart/reverse/terminate this hop.
                        mapping = {0: 1, 2: 5, 3: 6} if self.action in UP else {0: 4, 2: 7, 3: 8}
                        chosen = mapping[horizontal]
                    else:
                        chosen = horizontal
                elif chosen in VERTICAL:
                    self.vertical_finished = frame + 4
                self.action = chosen
                self.last = row['seq']
                event = {'frame': frame, 'seq': self.last, 'action': self.action,
                         'obs_frame': row['obs_frame'], 'requested_action': row['chosen']}
                if suppressed:
                    event['reason'] = 'stale_vertical_preserves_active_hop' if chosen in VERTICAL else 'vertical_requires_fresh_observation'
                self.applied.append(event)
        return self.action
