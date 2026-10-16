"""Apply the newest valid model action unchanged until its replacement arrives."""


class DirectActionTransport:
    def __init__(self):
        self.action = 0
        self.last = -1
        self.applied = []
        self.ignored = []

    def advance(self, frame, ready):
        if ready:
            row = max(ready, key=lambda r: r['seq'])
            if row['seq'] > self.last:
                chosen = row['chosen']
                if type(chosen) is not int or not 0 <= chosen <= 8:
                    raise ValueError('Invalid integer action')
                self.action = chosen
                self.last = row['seq']
                self.applied.append({'frame': frame, 'seq': self.last, 'action': chosen,
                                     'obs_frame': row['obs_frame'], 'requested_action': chosen})
        return self.action
