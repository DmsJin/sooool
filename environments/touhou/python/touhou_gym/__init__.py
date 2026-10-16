"""Simplified original Touhou fan environment. Requires Node.js >=18."""
from pathlib import Path
import json
import subprocess
import numpy as np
import gymnasium as gym
from gymnasium import spaces

class KaguyaEnv(gym.Env):
    metadata = {"render_modes": ["rgb_array"], "render_fps": 60}

    def __init__(self, render_mode=None):
        if render_mode not in (None, "rgb_array"):
            raise ValueError("render_mode must be None or rgb_array")
        self.render_mode = render_mode
        # move: idle,N,NE,E,SE,S,SW,W,NW; shoot; focus; bomb
        self.action_space = spaces.MultiDiscrete([9, 2, 2, 2])
        self.observation_space = spaces.Dict({
            "player": spaces.Box(0, 1, (6,), np.float32),
            "boss": spaces.Box(0, 1, (3,), np.float32),
            "bullets": spaces.Box(-1, 1, (256, 5), np.float32),
            "bullet_mask": spaces.MultiBinary(256),
            "effects": spaces.Box(0, 1, (3,), np.float32),
            "time": spaces.Box(0, 1, (1,), np.float32),
        })
        self._proc = None
        self.state = None

    def _request(self, payload):
        if self._proc is None:
            bridge = Path(__file__).parent / "engine" / "bridge.mjs"
            self._proc = subprocess.Popen(["node", str(bridge)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, text=True, bufsize=1)
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("Node simulator exited unexpectedly")
        result = json.loads(line)
        if "error" in result:
            raise RuntimeError(result["error"])
        self.state = result["state"]
        return result

    def _observe(self):
        s = self.state
        p, b = s["player"], s["boss"]
        bullets = np.zeros((256, 5), dtype=np.float32)
        mask = np.zeros(256, dtype=np.int8)
        # Closest threats first; >256 are omitted from observation only, not physics.
        threats = sorted(s["bullets"], key=lambda q: (q["x"]-p["x"])**2+(q["y"]-p["y"])**2)[:256]
        for i,q in enumerate(threats):
            bullets[i] = np.clip([q["x"]/480, q["y"]/640,q["vx"]/4,q["vy"]/4,q["r"]/10],-1,1)
            mask[i] = 1
        return {"player": np.array([p["x"]/480,p["y"]/640,p["lives"]/3,p["bombs"]/3,min(1,p["inv"]/150),s["graze"]/(s["graze"]+100)],np.float32),
            "boss": np.array([b["x"]/480,b["y"]/640,b["hp"]/b["maxHp"]],np.float32),
            "bullets":bullets,"bullet_mask":mask,"effects":np.array([p["dying"]/45,s["bombTimer"]/150,len(s["bombOrbs"])/8],np.float32),"time":np.array([s["tick"]/3600],np.float32)}

    def _info(self):
        return {k:self.state[k] for k in ("score","graze","status","tick","phase","hits","bombTimer")}

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._request({"command":"reset","seed":int(self.np_random.integers(0,2**32))})
        return self._observe(),self._info()

    def step(self, action):
        if self.state is None:
            raise gym.error.ResetNeeded("Call reset before step")
        if self.state["status"] != "playing":
            raise gym.error.ResetNeeded("Episode ended; call reset")
        if not self.action_space.contains(action):
            raise ValueError("Action must be [move (0..8), shoot (0/1), focus (0/1), bomb (0/1)]")
        r=self._request({"command":"step","action":[int(x) for x in action]})
        return self._observe(),r["reward"],r["terminated"],r["truncated"],self._info()

    def render(self):
        if self.state is None:
            raise gym.error.ResetNeeded("Call reset before render")
        image=np.full((640,480,3),[16,30,43],dtype=np.uint8)
        def disk(x,y,r,color):
            x,y=int(x),int(y);x0,x1=max(0,x-r),min(480,x+r+1);y0,y1=max(0,y-r),min(640,y+r+1)
            if x0>=x1 or y0>=y1:return
            yy,xx=np.ogrid[y0:y1,x0:x1]
            image[y0:y1,x0:x1][(xx-x)**2+(yy-y)**2<=r*r]=color
        for q in self.state["bullets"]:disk(q["x"],q["y"],5,[190,165,245])
        for q in self.state["shots"]:disk(q["x"],q["y"],2,[220,240,190])
        disk(self.state["boss"]["x"],self.state["boss"]["y"],20,[220,160,190])
        for orb in self.state["bombOrbs"]:disk(orb["x"],orb["y"],18,[245,180,220])
        if not self.state["player"]["dying"]:
            disk(self.state["player"]["x"],self.state["player"]["y"],8,[240,100,120])
        return image

    def close(self):
        if self._proc is not None:
            self._proc.stdin.close()
            self._proc.terminate()
            self._proc.wait(timeout=5)
            self._proc.stdout.close()
            self._proc=None

if "TouhouKaguya-v0" not in gym.registry:
    gym.register("TouhouKaguya-v0",entry_point="touhou_gym:KaguyaEnv")
