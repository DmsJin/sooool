# Prepare game environments

Install [uv](https://docs.astral.sh/uv/) and Git, then bootstrap the project:

```bash
uv sync --locked --python 3.12
uv run sol env list
uv run sol env setup tabletennis
export MUJOCO_EGL_DEVICE_ID=0  # use an allocated GPU
uv run sol simulate tabletennis --output runs/tabletennis-001
```

`setup` fetches the registered commit and installs the game's dependencies.
It reuses prepared sources and virtual environments. Launch commands select
the matching Python and source directory without shell activation.
They preserve the caller's working directory and relative output paths.
An unprepared or outdated environment reports the required setup command.

External sources, venvs and preparation records live in `~/.cache/sooool/`.
`XDG_CACHE_HOME` selects another cache location. Racing, Badminton and
TableTennis share the pinned RoboOlympics source but have separate venvs.
Asterix, Touhou and Rhythm use the existing project workspace.
System graphics drivers and browser system libraries remain host prerequisites.

Use an existing checkout for development:

```bash
uv run sol env setup vera20k --source /absolute/path/to/vera20k-agent
```

This records the checkout without switching or resetting it. Later launches use
that source until the next setup. Setup without `--source` selects the registered
commit. Managed source edits stop setup instead of being overwritten.

Setup compiles these environments and installs their Python 3.12 packages:

| Environment | Prepare | Build requirements and guide |
| --- | --- | --- |
| Red Alert 2: Yuri's Revenge (VERA20K) | `uv run sol env setup vera20k` | Rust, Maturin, and Linux native libraries. [Python API and installation guide](https://github.com/mindorigin150/vera20k-agent/blob/c9a9b38f2e42042f398a39a4f07edcd0feba0219/python/README.md). |
| Plants vs. Zombies (PvZ) | `uv run sol env setup pvz` | CMake, Ninja, and Linux native libraries. [Installation and native validation guide](pvz.md). |

The VERA20K revision includes the offscreen HUD update fix. Re-run
`uv run sol env setup vera20k` to rebuild an existing environment.

Both environments keep game resources outside this repository.
Their model experiment runners are later integrations. Setup prepares their native
APIs. Re-run setup after native source changes.

`environments/registry.json` owns source revisions, Python versions, install
steps and existing runner commands. Recipes own experiment conditions, and
policies own gameplay decisions. Add a registry entry and the game's own runner
when introducing an environment.
