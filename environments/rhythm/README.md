# DFJK Rhythm Lab

四轨 DFJK 节奏游戏，难度 1，默认 Rick Astley《Never Gonna Give You Up》Apple 官方约 30 秒试听段。不是完整歌曲。无需账号或 API key。浏览器直接从 Apple 加载音频；可在「音频与校准」选择个人音频。个人音频生成 113 BPM 练习谱，不承诺与其他录音同步。

## Play locally

```sh
python3 -m http.server 8765 --directory dist
```

打开 http://localhost:8765 ，点击开始，使用 D F J K；也支持触摸按键。前两秒预留准备。暂停、重开、切换页面自动暂停，音频缓冲时谱面跟随音频时钟。判定窗口 perfect 55ms / good 110ms / ok 180ms。空按断连，不降低命中率；miss 断连且计入准确率。偏移正值让判定提前。

## Gymnasium

```sh
pip install -e .
python example.py
```

`gym.make('DFJK-Rhythm-v0')`；120 Hz，`MultiBinary(4)` 对应 DFJK，1 按下、0 松开，只处理按下边沿。`Box(8,3)` 暴露未来八个未判定音符，每行为 `[距离击打的秒数, 轨道/3, valid]`，补零。这个是包含谱面信息的状态环境，不是视觉观测环境。音乐不在 Python 环境播放。奖励 perfect +1、good +0.7、ok +0.3、miss -0.5、空按 -0.1，音频结束 terminated=True；不使用 truncated。`reset(seed=...)` 支持复现。

浏览器和 Gym 共用 `dist/chart.json` / `rhythm_gym/chart.json`；修改时需保持两者一致。谱面是为试听段自动分析节拍后制作的稀疏练习谱，非官方谱。官网试听来源：Apple iTunes Search API，艺术家 Rick Astley。

## 谱面 v2

113 BPM 拍点上编排四分音符，乐句尾加入八分音符短连打（间隔约 265ms）；单键交替，不加双押、长按与滑键，保留入门难度。蓝色四分音符、金色八分音符，透视四轨、击打粒子与中央连击。默认谱面共 52 音符。

## Immersive stage

全高竖向游戏舞台，单曲选曲卡 → READY/GO → 演奏 → 评级结算。蓝色玻璃音符统一外观，八分音符通过间距表示。原创 SVG 夜景舞台、麦克风歌曲封面，Web Audio 合成界面提示音，无外部字体和图片依赖。DFJK/触摸操作，空格暂停继续；返回选曲取消未完成开场，失焦自动暂停；设置内支持个人音频和判定偏移。评级按加权准确率：S ≥95%、A ≥85%、B ≥70%、否则 C；全连需每个音符连击且无空按。Python Gym 仍使用默认 52 音符谱面，个人音频仅供前端练习。
