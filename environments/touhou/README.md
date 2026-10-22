# 永夜练习场 · 蓬莱山辉夜 Lv.1

可玩的简化东方同人弹幕环境：60 秒、3 残机、3 符卡、3 段原创弹幕。不是原作 AI、关卡或素材的精确复刻。

## 原作素材呈现层 v5

使用另一 session 导出的 TH08 素材：灵梦自机/御札/辅助机、6B 辉夜动画、敌弹、声明立绘、HUD、位图字体、背景贴图、消弹/命中特效及原版音效。图集按 `frames.json` 源矩形绘制，像素精灵关闭平滑；自机 6 帧换帧、Boss 5/6 帧换帧，动画由现有逻辑 tick 驱动。横向移动使用原作侧身帧。HUD 使用原图集与原数字字形。

表现层独立模块为 `dist/th08-renderer.mjs` 和 `dist/th08-audio.mjs`。现有引擎、弹道、碰撞、难度、时间及 Gym 状态保持不变；浏览器和 Python 引擎 SHA256 均为 `348e81340d4a09f8b488193daf0b4e395afa2755d34f249585ff5e1ffe787aa4`。显示贴图尺寸不参与碰撞。

BGM 由原 `thbgm.dat` 提取，OGG 长 179.97786848072562 秒，Web Audio BufferSource 显式循环 `37.85868480725624 → 179.97786848072562` 秒；回环保留原作前奏边界，暂停恢复保存位置，重开从头。音效使用原版 WAV，包括死亡、射击、擦弹、符卡、消弹和暂停音。音量可调、声音可关闭。

素材完整出处与源存档哈希见 `dist/assets/th08/manifest.json` 和 `HANDOFF.txt`。素材版权归 ZUN / 上海爱丽丝幻乐团，提取工具许可不授予游戏素材权利，不是 CC0 或项目原创素材。

这仍是低难度练习引擎：背景透视/旋转为轻量重建，未完整解释所有原版 ANM 指令或 Stage STD 3D 相机脚本；符卡名称用于视觉主题，弹道不是原作对应符卡。Bonus/History/Point/Time 是练习指标，不是原作存档或计分公式。开场 2.75 秒、符卡切换 2.25 秒为既有演出时段。

## 直接玩

`python3 -m http.server 8787 --bind 127.0.0.1 --directory dist`，浏览器打开 http://localhost:8787 。

方向键移动，Z 射击/确认，Shift 低速，X 符卡清屏，Esc 暂停。点击开始后获取键盘操作；失焦自动暂停。手机支持屏幕按钮。
击破 Boss 为 `won`，存活 60 秒为 `survived`，残机耗尽为 `lost`。前两种均完成练习。声音按钮控制辉夜 BGM 与原版音效。

## 坠机与自机符卡

被弹扣一残机，爆散后自机消失 45 帧，此期间不能移动、射击或放符卡；有残机时从底部复活并获得 150 帧无敌，最后一条残机耗尽会在爆散演出后结束。

X 为灵梦梦想封印式简化符卡：8 颗彩色球先展开旋转，随后逐颗追踪 Boss；每球命中伤害 30，沿途半径 38px 消弹，初始清屏，无敌 180 帧。符卡总时段 150 帧，期间不能叠放；仍不是原作所有数值/动画的精确复刻。

## 在 sooool 中运行实验

在仓库根目录运行 `uv run sol env setup touhou`，再使用 `uv run sol simulate touhou`。
模型评估和预算参数见[运行指南](../../docs/touhou-development.md)。以下说明用于单独使用 Gymnasium 包。

## Gymnasium

需要 Python >=3.10、Node.js >=18。无需浏览器、服务端或网络 API。Python 通过常驻 Node 子进程调用与前端完全相同的引擎（每步 1/60 秒）。

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python examples/random_agent.py
```

```python
import gymnasium as gym
import touhou_gym

env = gym.make('TouhouKaguya-v0', render_mode='rgb_array')
obs, info = env.reset(seed=42)
try:
    while True:
        obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
        if terminated or truncated:
            print(info)
            break
finally:
    env.close()
```

动作 `MultiDiscrete([9,2,2,2])`：`[移动,射击,低速,符卡]`。移动索引为 `0=停,1=上,2=右上,3=右,4=右下,5=下,6=左下,7=左,8=左上`。后三项 0/1。

观测 Dict：`player` 6 维（归一化 x/y、残机、符卡、无敌帧、擦弹比例），`boss` 3 维（x/y/HP），`bullets` 256×5（x/y/vx/vy/r），`bullet_mask` 256 维，`time` 1 维，`effects` 3 维（坠机剩余帧/45、符卡剩余帧/150、存活光球数/8）。按距离排序返回最近 256 颗子弹；截断只影响观测，不影响碰撞。`render()` 返回 640×480×3 uint8 RGB 数组。

奖励：每帧生存 +0.002，命中 Boss +0.015/发，擦弹 +0.03，符卡 +0.2，被弹 -1，失败 -3，击破 +5，时限生存 +2。光球命中每颗额外 +0.09，附加得分 60。奖励是简单基线，尚未调参。击破/失败返回 terminated；60 秒返回 truncated，`info.status='survived'` 区分存活结果。reset 同 seed 可复现；浏览器固定 seed=1，Gym reset 的 seed 经 Gym RNG 生成关卡种子。

## 弹幕谱

`dist/chart.json` 可在前端下载。三段依次是环弹、瞄准扇弹、旋转环弹。速度为 px/frame，逻辑固定 60Hz。`dist/engine.mjs` 是权威实现；Python 包内 `engine/` 是同一文件的分发副本，测试检查二者一致。

## 验证

```bash
node --test tests/engine.test.mjs
.venv/bin/python tests/check_gym.py
# 本地检查服务使用 8791 端口（需要 Playwright/Chromium）：
python3 -m http.server 8791 --bind 127.0.0.1 --directory dist
python3 tests/browser_check.py
python3 tests/th08_presentation_check.py
```

Gymnasium 官方 checker、完整 episode、种子复现、碰撞/无敌、符卡按键边沿、三段谱、通关、浏览器实际键盘和手机布局均有检查。
