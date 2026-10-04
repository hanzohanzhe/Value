# Prompt 25 installation and CI report

Status: **engineering path passed; non-programmer public-package gate deferred**.

The supported compatibility environment is 64-bit Windows, CPython 3.10 and Node
22. Direct and transitive dependencies are pinned in `requirements/*.lock` and
`package-lock.json`. Python groups separate open core, Scheme C compatibility,
perfect-foresight solver, independent validation, export and CI tooling.

Implemented evidence:

- `scripts/doctor.py` checks Python, architecture, Node, optional solvers, loopback
  ports, storage permissions and free disk with actionable messages.
- `install-force.cmd`, `start-gridform.cmd` and `uninstall-force.cmd` wrap exact
  PowerShell scripts. Mutable state uses `FORCE_DATA_HOME` or LocalAppData; it is
  not tied to a desktop or working directory.
- immutable run migrations are additive; the upgrade test verifies historical run
  bytes are unchanged.
- Python wheel and source distribution build with a pinned build backend. Package
  policy scans both archives for research data and absolute user paths.
- a clean virtual environment under a path containing spaces and Chinese
  characters installed the wheel and imported `backend.server`, `gridform_core`
  and `gridform_validation` from a different working directory.
- the doctor passed against a Unicode/spaces data root with more than 900 GiB free.
- CI covers locks, portable paths, Python tests, frontend build/render tests,
  browser E2E, synthetic fixtures, retained-source preservation, package build,
  policy scan and SBOM generation.
- CycloneDX inventories contain 25 Python and 714 Node components for the tested
  workspace.

The launcher serves the production frontend through `scripts/serve-force-ui.mjs`.
This contains a local Windows path-normalization workaround for the pinned Vinext
0.0.50 asset cache and probes a compiled JS asset before reporting readiness.

Limits: there is no signed installer; the frontend is built from the repository
rather than embedded in the Python wheel; a complete clean signed-package browser
install/upgrade/uninstall cycle has not run in an external Windows VM; vulnerability
reporting is informative and was not used as a release waiver. Most importantly,
the built distribution contains the copied compatibility implementation whose
redistribution rights are unresolved. It is a local engineering artifact, not a
public release package.
