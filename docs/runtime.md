# Reproducible player runtime

The Android NES host uses the same unmodified **EmulatorJS 4.2.3** runtime as the working prototype. Preparing the build does not upgrade EmulatorJS, rebuild a core or alter its settings. Guests receive streamed media and do not need an emulator runtime.

Create a build-only virtual environment, install the tested archive reader, then prepare the runtime:

```sh
python3 -m venv .venv-runtime
.venv-runtime/bin/python -m pip install -r scripts/requirements-runtime.txt
.venv-runtime/bin/python scripts/prepare-runtime.py
```

`py7zr==1.0.0` is pinned to the version used to validate this extraction. It is a build-time dependency, not part of the broker or guest. The preparation script downloads the [official 4.2.3 archive](https://github.com/EmulatorJS/EmulatorJS/releases/download/v4.2.3/4.2.3.7z) to a user cache and verifies this exact SHA-256 before extraction:

```text
07d451bc06fa3ad04ab30d9b94eb63ac34ad0babee52d60357b002bde8f3850b
```

For an existing official archive, avoid another download:

```sh
.venv-runtime/bin/python scripts/prepare-runtime.py --archive /path/to/4.2.3.7z
```

The local archive is subject to the same checksum check. The script rejects unsafe entry paths, links, duplicate paths and excessive extraction sizes, validates the runtime version and expected layout, then installs a fully validated staging tree using directory renames. When replacing an existing runtime it keeps the previous directory until the final rename succeeds and restores it if that rename fails. A lock prevents concurrent preparation; do not run this while a build is reading `runtime/`. An interrupted process can leave a staging/lock directory for inspection; do not delete the lock until confirming no preparation process is active.

Output is the ignored root `runtime/`, including `data/`, `LICENSE`, preserved upstream assets, `UPSTREAM.json` and copied nested FCEUmm license/build metadata under `third-party/fceumm/`. The entire official runtime is retained to preserve loader expectations and exact core bytes. App packaging may expose only the routes the host needs; retaining other upstream assets does not claim support for more systems.

The app currently selects `data/cores/fceumm-legacy-wasm.data`. The archive is fixed by SHA-256, and the selected core file's SHA-256 is recorded in `UPSTREAM.json`. Upstream reports core build version 2.0.2 and minimum EmulatorJS 4.2.2. This establishes binary identity, **not** the exact corresponding source revision. See [third-party notices and source requirements](third-party-notices.md) before distributing a packaged build.

Checks without a download:

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
```
