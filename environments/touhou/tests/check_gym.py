import gymnasium as gym
from gymnasium.utils.env_checker import check_env
import numpy as np
import touhou_gym

env=touhou_gym.KaguyaEnv(render_mode='rgb_array')
try:
    check_env(env, skip_render_check=False)
    obs,info=env.reset(seed=42)
    assert env.observation_space.contains(obs)
    assert env.render().shape==(640,480,3)
    env.action_space.seed(1)
    total=0
    for t in range(3600):
        obs,r,terminated,truncated,info=env.step(env.action_space.sample())
        assert env.observation_space.contains(obs),t
        total+=r
        if terminated or truncated:break
    assert terminated or truncated
    print('Gym checker + complete episode passed',info,'reward',round(total,3))
finally:
    env.close()
with gym.make('TouhouKaguya-v0') as registered:
    registered.reset(seed=1)
    registered.step(np.array([0,1,1,0]))
print('Registered environment passed')
