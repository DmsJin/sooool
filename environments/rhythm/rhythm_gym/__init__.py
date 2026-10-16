import json
from pathlib import Path
import gymnasium as gym
import numpy as np
from gymnasium import spaces

class RhythmEnv(gym.Env):
    """DFJK key-down actions at 120 Hz. Observations expose next 8 notes.

    Columns: seconds until note, lane / 3, valid mask. Padding is zero.
    Reward: perfect 1, good .7, ok .3, miss -.5, empty press -.1.
    A held key triggers once; release before hitting the next note.
    """
    metadata = {"render_modes": ["ansi"], "render_fps": 120}

    def __init__(self, render_mode=None, chart_path=None):
        self.chart = json.loads(Path(chart_path or Path(__file__).with_name('chart.json')).read_text())
        self.render_mode = render_mode
        self.action_space = spaces.MultiBinary(4)
        self.observation_space = spaces.Box(-10000, 10000, (8, 3), dtype=np.float32)
        self.dt = 1 / 120
        self.reset()

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.time = 0.
        self.notes = [dict(n, state=0) for n in self.chart['notes']]
        self.held = np.zeros(4, dtype=np.int8)
        self.score = self.combo = self.judged = 0
        self.weighted_hits = 0.
        self.done = False
        return self._obs(), self._info()

    def _obs(self):
        obs = np.zeros((8, 3), dtype=np.float32)
        for i, n in enumerate([n for n in self.notes if n['state'] == 0][:8]):
            obs[i] = [n['time'] - self.time, n['lane'] / 3, 1]
        return obs

    def _info(self):
        return dict(time=self.time, score=self.score, combo=self.combo,
                    judged=self.judged, accuracy=self.weighted_hits / max(1, self.judged))

    def step(self, action):
        if self.done:
            raise RuntimeError('Call reset() after termination')
        action = np.asarray(action, dtype=np.int8)
        if not self.action_space.contains(action):
            raise ValueError('Expected four binary DFJK keys')
        reward = 0.
        for n in self.notes:
            if not n['state'] and self.time - n['time'] > .18:
                n['state'] = -1
                self.combo = 0
                self.judged += 1
                reward -= .5
        for lane in np.flatnonzero((action == 1) & (self.held == 0)):
            n = next((n for n in self.notes if not n['state'] and n['lane'] == lane and abs(n['time'] - self.time) <= .18), None)
            if n is None:
                reward -= .1
                self.combo = 0
                continue
            delta = abs(n['time'] - self.time)
            value = 1. if delta <= .055 else .7 if delta <= .110 else .3
            n['state'] = 1
            self.score += round(value * 1000)
            self.weighted_hits += value
            self.combo += 1
            self.judged += 1
            reward += value
        self.held = action.copy()
        self.time += self.dt
        self.done = self.time >= self.chart['duration']
        if self.done:
            for n in self.notes:
                if not n['state']:
                    n['state'] = -1
                    self.judged += 1
                    self.combo = 0
                    reward -= .5
        return self._obs(), reward, self.done, False, self._info()

    def render(self):
        return f'{self.time:6.2f}s | score {self.score:06d} | combo {self.combo}'

gym.register(id='DFJK-Rhythm-v0', entry_point='rhythm_gym:RhythmEnv')
