# 辉夜追踪 benchmark：第二轮实时结果

完成两轮 prompt 迭代与真实 API 复测。默认 seed 1 的原速实时局从 59.30 秒缩短到 51.05 秒（8.25 秒，13.9%），但中弹从 1 次增加到 2 次。指定中段改善明显，开局仍有新的长空枪；不能据此宣称稳定胜率或全面提升。

## Benchmark 与奖励

固定 12 个开发场景：8 个来自前次真实局，4 个来自用户已验证的人类录制。原始 PNG、按键、已返回计划、模型自己的过去视觉估计、历史延迟摘要均有哈希和来源记录。未来画面、人物真坐标、轨迹、种子、原局未来按键和私有评分不进入 actor。

两档固定延迟 2.69135 / 3.170205 秒；每个答案从相同真实前缀出发，等待延迟，执行 GPT 动作，再观察 180 个逻辑 tick。主奖励是实际普通子弹命中伤害 / 360，Bomb 按逐个 orb_hit 的 30 HP 单独计，不用炸弹刷跟枪得分。连续空枪、停止射击、死亡、生命和 gross Bomb 次数单列。晋升先检查中弹/死亡/Bomb/不射击没有增加，再比较射击伤害，空枪为次级排序。瞬时距离和追旧位置只做诊断，不强迫模型向当前 boss x 追赶。

每轮 3 策略 × 12 场景 × 2 次独立回答 = 72 个实际订阅答案，回放 144 次。两轮共 144 策略请求、288 次固定条件回放。第一轮两个新候选伤害增加约 6% / 11%，因额外死亡未晋升。第二轮 safe_intercept_v2 相对同轮 adaptive 普通射击伤害均值 101.875 → 105.9375（+3.99%），中弹 8 → 7，Bomb 8 → 8，通过冻结门槛。

样本相关且随机性明显：两轮 baseline 中弹总数分别 2 与 8，不能把 4% 当成显著效果。奖励用于选择和改进 prompt，没有训练权重。

额外按源局实际延迟重放四个关键场景（16 个复用答案，无新模型调用）：case16 214 个 visual 帧，case20 176，case24 152，case28 144。输出单独标记为 post-selection diagnostic，不能用它改写原冻结排名；伤害提高的同时部分场景仍多中弹。

## 整局与真实 API

同样的新开发种子 9 / 10、同样的延迟随机数和原引擎，容量槽一直保留到模拟 terminal。旧 adaptive 两局无伤但超时剩 HP470 / HP175。safe_intercept_v2 两局分别 59.97 / 50.38 秒通关，均中弹 2 次。整局合计 304 个订阅请求；加上场景测试，本轮共 448 个游戏策略订阅请求。

随后冻结 21 个不同观测的完整任务输入，移除且仅移除模拟器追加说明，原游戏 task、观测、动作 schema 和精简外层约束保留。API 严格串行校准 21/21 合法，费用 $1.187976。19 个三图样本的 legal-action 最快 1.467 秒、中位 2.283 秒、P95 2.955 秒；1/2 图各一个样本不能估计慢尾。串行 legal 分布映射到过去 concurrent early timing 是声明的模型，不是新并发实测。

| 真实 API 默认 seed1，独立重开 | 上次 adaptive | safe_intercept_v2 |
| --- | ---: | ---: |
| 通关游戏秒 | 59.30 | 51.05 |
| 中弹 / 剩余命 | 1 / 2 | 2 / 1 |
| 消耗 Bomb | 3 | 3 |
| 普通射击名义伤害 | 2480 | 2485 |
| 普通射击 DPS | 41.82 | 48.68 |
| 指定游戏视觉区间 17–28 射击伤害 | 215 | 740 |
| 同区间最长空枪（逻辑秒） | 6.48 | 1.48 |
| 全局最长空枪（逻辑秒） | 6.48 | 9.18 |
| 实测 screenshot→apply 中位秒 | 2.691 | 2.204 |

新局 2485 名义射击伤害包含终结帧 5 HP 过量伤害；实际 boss HP 下降仍为 3200，Bomb 伤害 720。两次整局轨迹不同，中段表格是描述性比较，不是相同状态配对实验。延迟本次也更低，不能把全部速度收益单独归因于 prompt。

新局最长空枪位于逻辑 5.48–14.65 秒，已保存四个原始新回归场景 opening-regression-cases（尚未收集新候选答案或评分）。尚未解决：开局对反转/停留位置预测不足；整局多中弹。此轮停止付费，保留预算供后续针对这些问题的迭代。

## 验收与复现

80 个真实请求全部合法、终态与 early 答案一致、用量/费用逐项与 ledger 一致。19 次动作中 18 次在响应终态前生效；最终 terminal_accounting_complete=true。实际速度 0.999397×、无暂停/失焦、最大 RAF 间隔 66.7ms；不声称每帧完美 60fps。HTTP served engine 与源引擎 SHA256 均为 348e81340d4a09f8b488193daf0b4e395afa2755d34f249585ff5e1ffe787aa4。

本次真实局 $1.8589824；本轮新增 API 校准＋实时局 $3.0469584；全部付费实验累计 $21.6291402，unknown/inflight0、blockednull，低于用户 $30 上限。订阅使用 gpt-6.1-sol/low、aggressive 精简 Codex 外层；API 直接游戏任务，未把外层精简宣称为已证实的提速。

GPT 仍从画面决定方向、Z、Shift、X、时长。程序仅校验、四路竞速仲裁和机械执行；没有隐藏状态瞄准/躲弹、时刻坐标脚本或自动 target servo。评分与完整状态仅离线分析。录影 realtime-tracking-v2.mp4 为原速浏览器录制等速 30fps 转码，未经重演或删切，无音轨；原始 WebM 在 realtime-v2/video。

窗口秒数是 research.visual_frame/60，包含符卡暂停；原始 MP4 有页面加载前导段，不能直接把窗口数字当精确 MP4 seek 时间。

代码已提交到本地游戏仓库的研究分支，完成后按工作树规则本地整合，不发布研究接口到 Sites。代码入口：research/tracking_cases.py、tracking_benchmark.py、tracking_summary.py、early_control_delays.py、early_transport_delay.py、realtime_profile_fixtures.py、run_episode.py。运行方法见 TRACKING_BENCHMARK.md、EARLY_DELAY_CALIBRATION.md、REALTIME_PROFILE_FIXTURES.md。141 个研究回归测试通过、6 项跳过；额外真实浏览器前缀/最终状态校验通过。

远端实验根目录 /home/ubuntu/wzh/touhou-sol-study：tracking-comparison-minimal-v1/v2、tracking-baseline-episodes-v1、tracking-candidate-episodes-v2、api-real-tracking-safe-intercept-v2-seed1。API 运行源码 src-v24；engine/frontend 来自共享只读实验 src/dist，已按实际 served 内容验 hash。原在线游戏未重发版。
