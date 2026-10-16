"""Atomic four-frame row hop, neutral landing, and fresh-row command guard."""
from hop_controller_v2 import VERTICAL


class HopControllerV3:
    def __init__(self):
        self.action = 0
        self.last = -1
        self.vertical_finished = -1
        self.applied = []
        self.ignored = []

    def _landing_action(self, action):
        return 0

    def advance(self, frame, ready):
        if self.action in VERTICAL and frame >= self.vertical_finished:
            self.action = self._landing_action(self.action)
            self.applied.append({'frame':frame,'seq':self.last,'action':self.action,
                                 'reason':('row_hop_finished_neutral' if self.action==0 else 'vertical_timeout_horizontal_continues')})
        if ready:
            row = max(ready,key=lambda r:r['seq'])
            if row['seq'] > self.last:
                chosen = row['chosen']
                if type(chosen) is not int or not 0 <= chosen <= 8:
                    raise ValueError('Invalid integer action')
                self.last = row['seq']
                stale = row['obs_frame'] < self.vertical_finished
                if not stale:
                    self.action = chosen
                    if chosen in VERTICAL:
                        self.vertical_finished = frame+4
                event = {'frame':frame,'seq':self.last,'action':self.action,
                         'obs_frame':row['obs_frame'],'requested_action':chosen}
                if stale:
                    event['reason'] = 'command_requires_post_hop_observation'
                    self.ignored.append(event)
                else:
                    self.applied.append(event)
        return self.action
