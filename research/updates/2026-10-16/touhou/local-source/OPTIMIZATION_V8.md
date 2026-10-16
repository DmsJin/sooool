# Numerical forecast experiment v8

Two experimental prompt variants append explicitly hypothetical arithmetic
examples to either balanced-v7 or historical-v2. Coordinates, velocities and
times in examples are invented, not private fixture forecasts. GPT still
chooses all action fields; engine/reward/execution remain unchanged.

Original26 fixtures,3 candidates,2 repeats yielded156 valid responses and264
original-engine counterfactuals; four clone finals matched original replay.
Neither candidate passed the unchanged development gate. Against the fresh
baseline (5 delayed hits,20 Bombs,52.79 mean ordinary damage), intercept-math-v8
had4 hits,20 Bombs,47.98 damage; kinematic-v8 had9 hits,0 Bombs,50.19 damage.

Kinematic-v8 produced some ordinary contact in E02, but E04/E08 still missed.
Some outputs improved their target estimate without selecting enough movement
to approach it. Such differences need separate forecast/endpoint diagnostics,
not automatic action repair. The default candidate remains historical v2.

Full records are in task artifact kaguya-optimization-v8; model inputs retained
original screenshots/metadata/schema. Paid API calls for this experiment: zero.
Frozen policies SHA256:
138fac4d4f9fea8064897bda485cd46ba97ec085c9a67e672f34307b72fe3efa.
