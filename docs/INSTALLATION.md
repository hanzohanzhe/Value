# Installing VALUE Network Extensions

This procedure is validated for VALUE Network Extensions 0.6.0-alpha.2.
Prompt 64 records the clean-checkout, package, browser, synthetic-data and local
UK-data gates in `publication/prompt64-release-report.md`. The separately
assembled UK research-data asset remains governed by per-object source terms; no
project-wide licence covers every local or upstream UK file.

## Supported local environment

- 64-bit Windows 10/11;
- CPython 3.10 (the only native and retained-reference version currently backed by numerical evidence);
- Node.js 22 or later;
- a writable local data directory with at least 2 GiB free for installation and short tests.

The website and API bind only to loopback. Research data stays in
`FORCE_DATA_HOME`. An existing source checkout keeps its `.gridform` directory;
a clean install defaults to `%LOCALAPPDATA%\FORCE`. Historical run directories
are immutable and state migration is additive.

## Non-programmer path

1. Install 64-bit Python 3.10 and Node.js 22 LTS.
2. Double-click `install-value.cmd`. This creates `.venv`, installs the committed
   `force-native` lock, runs the environment doctor and builds the English website.
3. Double-click `start-value.cmd`.
4. Open the printed `http://127.0.0.1:8800` address if the browser does not open.
5. Double-click `stop-value.cmd` before moving the installation.

Repeated installation and launch are idempotent. The launcher stops only PIDs it
recorded and refuses to take a port owned by an unrelated process.

## Install a complete data pack offline

The Data page accepts one local `force.data-bundle/v1` ZIP. Select **Install a
FORCE data pack**, review the licence and attribution files supplied by its data
steward, acknowledge them, and start the upload. The browser streams the file to
loopback staging and shows upload progress; it does not unpack the archive.
FORCE then checks safe paths, expansion limits, every SHA-256, the data-pack
manifest, rights records and all 25 semantic interfaces before an atomic rename.
Until that rename, the previous pack is unchanged. Cancelling during upload or
any failed check removes staging. Allow the expanded pack size plus at least
1 GiB free; the UK benchmark is a separate large release asset.

Maintainers can build the same deterministic format without changing source
objects:

```powershell
py -3.10 scripts\build_data_bundle.py --pack-root data-packs\my-pack --output my-pack.zip
```

Installing a bundle is idempotent when its bytes match. A different bundle with
the same pack ID is rejected; publish it under a new versioned ID so old Studies
and completed runs retain their original identity. FORCE does not automatically
download research data or accept upstream terms for the user.

## Capability choices

The default capability is `force-native`: v2 orchestration, live registered
modules and the default Scheme-C-derived PSM, without retained-reference-only
packages. Use `scripts\install-force.ps1 -Capability scheme-c-reference` only for
the explicit whole-kernel comparison. `solver` adds SciPy for the optional
perfect-foresight PSM; `full` installs native, reference, solver and validation
dependencies. PuLP/CBC is validation-only and never becomes the production
clearing engine by silent fallback.

## Contributor path

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements\force-native-py310.lock
npm ci
.\.venv\Scripts\python scripts\doctor.py --capability force-native
npm test
.\.venv\Scripts\python -m unittest discover -s tests -p "test_*.py" -v
```

Release maintainers build the wheel and source distribution through the
normalising wrapper below. It fixes archive timestamps, ownership metadata and
member order, then emits hashes. Two builds from the same source and locks must
be byte-identical.

```powershell
.\.venv\Scripts\python scripts\build_python_release.py --outdir dist
.\.venv\Scripts\python scripts\package_policy_scan.py --dist-dir dist
```

Use `FORCE_DATA_HOME` for a path containing spaces or non-ASCII characters to
test relocation. Do not put research data under the Python package.

## Upgrade and uninstall

Install a newer application over the code directory and point it at the same
`FORCE_DATA_HOME`. Migrations may add indexes or metadata but never rewrite a
completed run. `uninstall-value.cmd` removes only dependencies and build output;
research data is retained. Data deletion requires `-RemoveResearchData`, an
explicit `FORCE_DATA_HOME`, and typing the exact resolved path.

The current local-code, scientific and GitHub decisions are recorded in
`publication/prompt52-final-test-report.md` and its companion JSON. Installation
success does not expand the redistribution rights recorded for each data object.
