# VALUE Linux local candidate

This Linux x86-64 candidate contains application source, an existing production UI build and five production Node packages. It requires externally installed runtimes; it is not a complete offline runtime distribution. No runtime, dependency or data download occurs during packaging or installation. Windows EXE validation is separate.

Supply an existing Linux x86-64 Python **3.10** executable with numpy, pandas, scipy, xarray, netCDF4 and pyproj installed, and Node **22.13.0 or newer**. The control scripts themselves require `python3` (3.10 or newer) on PATH. Installation checks imports and records runtime executable hashes and dependency versions; this does not certify scientific numerical equivalence. Keep the supplied runtimes available at their original paths. Start rejects changed runtime identities or dependency versions.

After extracting the archive, install into a new or empty user directory:

```sh
cd VALUE-linux-local
./install-value --prefix "$HOME/.local/value-candidate" \
  --python /absolute/path/to/python3.10 --node /absolute/path/to/node
"$HOME/.local/value-candidate/bin/start-value"
"$HOME/.local/value-candidate/bin/diagnose-value"
"$HOME/.local/value-candidate/bin/stop-value"
```

The UI defaults to http://127.0.0.1:8800; the only supported alternative is `--ui-port 18800`. Both origins are already allowed by the local API. Installation and runtime configuration checks reject other ports. The prebuilt UI requires the API at http://127.0.0.1:8766. Occupied ports cause start to fail without stopping other applications. Repeated start is idempotent while both recorded processes remain owned by this installation. Stop checks PID start time, process group, exact command and installation token before signaling API/UI groups. It preserves state. Separate detached scientific workers are not managed by these UI control scripts; stop is not a Run cancellation operation.

State defaults to `<prefix>/state`. For independent storage, pass `--data-home /absolute/new/empty/directory` outside the prefix. Existing nonempty prefixes or state directories are refused. No system service, sudo operation, global package installation or automatic uninstall is provided. Configuration and diagnostic logs reside in the prefix. Diagnose reports changed source/build files, runtime identities, process ownership, local health and bounded log tails.

For a Run with a complete execution archive, **Runs → Run with the archived method** gives the `python3 scripts/prepare_archived_workspace.py review` and `prepare` commands. Run them from this installation's `app` directory and use its state directory as `--data-home`. Preparation requires explicit trust in the archived code, creates a separate workspace and Study, and starts neither services nor a Run. Stop the current instance before using the generated `bin/start-archived-value`; the two workspaces share API port 8766. The restored workspace uses archived Python and scientific source, with the current release UI and an external Node executable. It checks recorded execution identity and pinned local host dependencies. This is same-host Linux restoration; historical locale evidence, complete OS isolation and cross-platform portability are not claimed. The generated README includes start, diagnose and stop commands.

The default archive contains no user state, private datasets or scientific results. A release built with `--include-teaching` includes only the VALUE 101 baseline/network CC0 teaching pair after checking declared licences and binding bytes/hashes. Installation invokes the existing VALUE 101 installer, copying pack bytes into the new state `data-packs` and network `data-workbench/installed-packs`; it does not fabricate manifests. This makes the teaching sources available to Learn. Research datasets must be supplied separately through the application.

Maintainers build the final production UI first, then package without another build or model run:

```sh
python3 scripts/build_linux_frontend_release.py \
  --output /absolute/path/VALUE_linux_local_candidate.tar.gz \
  --build-log /absolute/path/production-build.log --include-teaching
```

`release-manifest.json` records every bundled file hash, source commit/dirty entries, external runtime requirements and existing build provenance. The adjacent `.sha256` file checks the archive. Installation and start verify the inventory. The bundled prebuilt UI is explicitly recorded as an existing build; source/build equivalence requires the maintainer's final build evidence. This is an installation candidate, not a claim that the GBP1 scientific release gate or ten-year scientific acceptance has passed.
