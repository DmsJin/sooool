# PvZ environment

PvZ uses the upstream [Gymnasium interface](https://github.com/mindorigin150/PvZ-Portable-agent/blob/619afa2459c5493fedf0c5e4db34287a876d2a1c/docs/gym.md),
pinned to commit `619afa2459c5493fedf0c5e4db34287a876d2a1c` from `feat/gym-v1`.
The environment runs day level 1-8 with RGB observations and literal mouse events.
Each step advances one 10 ms logic tick. Model experiment runners are a later integration.

## Prepare

Follow the [project bootstrap](environments.md) and install native build dependencies.
On Debian or Ubuntu:

```bash
sudo apt install build-essential cmake ninja-build libjpeg-dev libopenmpt-dev \
  libpng-dev libsdl2-dev xvfb xauth libgl1-mesa-dri libegl-mesa0
uv run sol env setup pvz
uv run sol env list
```

Setup fetches the pinned source, builds the Release executable, and installs
`pvz-portable-gym[test]` into a separate Python 3.12 environment.
It disables debug cheats and community gameplay fixes. The build uses 12 compiler jobs.
The Python package uses an editable install because its validation CLI reads source revision metadata.
Repeated setup reuses the source and build directory.

The default cache contains:

```text
~/.cache/sooool/
├── sources/pvz/619afa2459c5493fedf0c5e4db34287a876d2a1c/
└── venvs/pvz/
    ├── bin/python
    ├── bin/pvz-validate
    └── build/pvz-portable
```

`XDG_CACHE_HOME` selects another cache location. `sol env list` reports the actual
source and Python paths. Use `sol env setup pvz --source /absolute/path/to/checkout`
for local development. Re-run setup after native source changes.

## Validate the native environment

Provide a resource directory containing `main.pak` and `properties/` from a compatible
GOTY installation. Keep resources outside this repository. Setup compiles and installs
the environment. Native validation uses the supplied resources.

Copy the prepared source and Python paths from `sol env list` into these variables:

```bash
PVZ_SOURCE=/absolute/path/to/pvz-source
PVZ_PYTHON=/absolute/path/to/pvz-venv/bin/python
PVZ_VENV=$(dirname "$(dirname "$PVZ_PYTHON")")
PVZ_RESOURCES=/absolute/path/to/goty-resources
PVZ_OUTPUT=/absolute/path/to/new-validation-output
```

On a Linux server with no desktop, use Xvfb and Mesa software rendering:

```bash
export LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=1 SDL_AUDIODRIVER=dummy
export __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json

xvfb-run -a -s '-screen 0 1024x768x24 -nolisten tcp -noreset' \
  "$PVZ_PYTHON" -m pytest "$PVZ_SOURCE/python/tests/test_env.py" \
  --binary "$PVZ_VENV/build/pvz-portable" --resource-dir "$PVZ_RESOURCES"

xvfb-run -a -s '-screen 0 1024x768x24 -nolisten tcp -noreset' \
  "$PVZ_VENV/bin/pvz-validate" \
  --binary "$PVZ_VENV/build/pvz-portable" --resource-dir "$PVZ_RESOURCES" \
  --output-dir "$PVZ_OUTPUT"
```

The tests cover mouse inputs, clocks, seed replay, truncation, complete loss,
worker failure, and cleanup. The validation CLI compares the worker with the original
client scheduler for seeds 0, 1, and 42. It also measures 1, 4, and 16 independent workers.
It saves `validation.json` and `initial.png`. Record the resource version beside these files.
These results are native environment evidence with zero model calls.

The upstream `diagnostics()` and `advance()` methods serve native validation.
Keep privileged diagnostics outside visual actor inputs.
