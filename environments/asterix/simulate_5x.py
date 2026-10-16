"""Pixel observations, timing quantization and deterministic replay for Asterix."""
from collections import deque
import hashlib
import io
import json
import math
FPS=12

def png(obs):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(obs).resize((224, 224), Image.Resampling.BILINEAR).save(buf, format='PNG')
    return buf.getvalue()

def delay_frames(seconds, scale=1.):
    if not math.isfinite(seconds) or seconds <= 0 or not math.isfinite(scale) or scale < 1:
        raise ValueError('Positive latency and finite scale >= 1 required')
    return max(1, math.ceil(seconds * scale * FPS))

def select_images(window):
    n = len(window)
    return [window[i] for i in sorted({0, max(0, n-3), n-1})]

def make_env(seed):
    import gymnasium as gym
    import ale_py
    gym.register_envs(ale_py)
    env = gym.make('ALE/Asterix-v5', render_mode='rgb_array', obs_type='rgb', frameskip=1,
                   repeat_action_probability=0., full_action_space=False, mode=0, difficulty=0,
                   max_num_frames_per_episode=108000)
    obs, info = env.reset(seed=seed)
    noops = int(env.unwrapped.np_random.integers(1, 31))
    for _ in range(noops):
        obs, _, done, truncated, info = env.step(0)
        if done or truncated:
            obs, info = env.reset()
    assert env.unwrapped.get_action_meanings() == ['NOOP','UP','RIGHT','LEFT','DOWN','UPRIGHT','UPLEFT','DOWNRIGHT','DOWNLEFT']
    return env, obs, info, noops

def verify_replay(root):
    """Verify old paid actions, rewards, lives and all issued image hashes, no model."""
    summary = json.loads((root/'summary.json').read_text())
    steps = [json.loads(l) for l in (root/'steps.jsonl').read_text().splitlines()]
    requests = [json.loads(l) for l in (root/'requests.jsonl').read_text().splitlines()]
    by_frame = {r['obs_frame']:r for r in requests}
    assert len(by_frame) == len(requests)
    env, obs, info, noops = make_env(summary['seed'])
    assert noops == summary['reset_noops']
    window = deque(maxlen=9)
    score = 0.
    checked = 0
    try:
        for frame, step in enumerate(steps):
            assert step['frame'] == frame
            if frame % 4 == 0:
                window.append((frame, png(obs)))
            if frame in by_frame:
                images = select_images(window)
                hashes = [hashlib.sha256(im).hexdigest() for _, im in images]
                assert hashes == by_frame[frame]['image_sha256'], f'image mismatch at frame {frame}'
                checked += 1
            obs, reward, done, truncated, info = env.step(step['action'])
            score += reward
            assert reward == step['reward'] and score == step['score'] and info.get('lives') == step['lives'], frame
        assert score == summary['score'] and len(steps) == summary['frames']
        assert checked == len(requests)
        return {'seed':summary['seed'], 'verified_frames':len(steps), 'verified_requests':checked,
                'score':score, 'lives':info.get('lives'), 'reset_noops':noops, 'model_calls':0}
    finally:
        env.close()
