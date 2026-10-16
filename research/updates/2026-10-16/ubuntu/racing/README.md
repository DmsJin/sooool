> Correction: historical subscription visual trials using `Native` with `localImage detail=low` omitted image contents. They do not establish GPT visual driving. The adapter is corrected and inline image hashes verified. Direct API calls bypass that Codex image preprocessor. See [strict native-action report](native_action/REPORT.md). Prior hybrid wins remain outside the current strict native-actuator goal.

# Independent Robot Racing research

This is our own research project. roboolympics is only the environment dependency.
Do not submit this project to that repository, create PRs there, or push its code
there. No upstream integration is required for this work.

Important: a coded5Hz visual policy supplies continuous steering. A no-GPT fixed-goal
preflight also won; GPT necessity is not established. This is not a pure GPT1x solve.

Final verified result: Level1 at1x real speed, GPT lane-commit decisions plus a5Hz
visual executor.3/3 development seeds and3/3 fresh frozen holdouts won with matching
replays. The actual gpt-6.1-sol/low/ultrafast API trial on unseen seed304 won2:0,
82calls,260/260 commands applied, valid_trial=true, deterministic=true. Physics:
51.79game seconds in51.795318wall seconds. Conservative paid ledger:$19.58103/$30,
no outstanding requests. See [RESULTS.md](RESULTS.md) for evidence and limitations.

## Project boundary

- Persistent project on the experiment machine: `/home/ubuntu/wzh/robot-racing-research`.
- Read-only environment dependency: `/home/ubuntu/wzh/racing-autoresearch-20261015`.
- Local project: `/tmp/robot-racing-research`; local dependency: `/tmp/robot-racing-environment`.
- Root scripts are the current entrypoints. Historical iteration/source snapshots
  are archival evidence; their original paths remain recorded for provenance.
- Data, budgets and outputs belong in this project, never in the environment root.
- Original result records were retained as archives. Final remote result copies
  were checked byte-for-byte by SHA256; see PROJECT_BOUNDARY.json on the server.

## Reproduce

Actual API-validation runtime: Python3.13.5, MuJoCo3.3.7,numpy2.5.4,SciPy1.18.1,
Pillow12.3.0,requests2.34.2. Subscription tests require an existing ChatGPT Codex
login; there is no paid fallback. Start from the independent project directory:

```bash
export RACING_ENV_ROOT=/home/ubuntu/wzh/racing-autoresearch-20261015
export RACING_CODEX_BINARY=/home/ubuntu/.local/bin/codex
export MUJOCO_GL=egl LP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
PY=/home/ubuntu/wzh/racing-autoresearch-20261015/venv/bin/python

$PY run.py sim --out results/new-subscription-trial \
  --profile results/profile-serial-v2/profile.json \
  --seed 101 --level 1 --slowdown 1 --variant metric \
  --control lane --chunk 1 --history 2 --cadence .6 --workers 3

# Makes real paid calls; key is requested using getpass, never stored.
$PY live.py --out results/new-api-trial \
  --profile results/profile-serial-v2/profile.json \
  --seed 304 --level 1 --slowdown 1 --variant metric \
  --control lane --chunk 1 --history 2 --cadence .6 --validation-cap 27

$PY -m unittest test_contracts test_stream test_lane
```

Output directories must be new. Keep `research-results/budget.json`: it already
contains this session's spending. Do not reset it to obtain a fresh$30 allowance.

Relocation changes only environment/budget/executable path configuration; the
camera measurements, goal policy, expiry logic and API streaming client remain
those of the verified candidate. Original tested source snapshots and hashes are
retained in the result evidence. No new paid run was used for relocation.
