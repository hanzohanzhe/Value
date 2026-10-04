# FORCE security and supply-chain policy

## Release boundary

FORCE 0.5 is a local, loopback-only research application. The browser server,
Python model service, source archive, synthetic data pack, UK benchmark asset
and executable third-party modules have different trust boundaries. A module
bundle executes Python in the FORCE process and is not sandboxed. A data bundle
is non-executable and is fully hashed before atomic installation.

## Dependency gates

`package-lock.json` is the sole JavaScript lock. The Python capability locks
separate default native execution, retained-reference plotting, optional solver
and independent validation dependencies. CI runs
`scripts/verify_install_scripts.py` before `npm ci`; any new or version-changed
install script fails closed. `scripts/run_dependency_audit.py` then obtains live
npm and pip-audit reports, blocks every npm high/critical finding, and requires
an unexpired machine-readable disposition for every other finding.

The reviewed package/version identities are also pinned in npm's standard
`allowScripts` field in `package.json`. The verifier requires that npm-native
policy and the detailed FORCE review ledger agree, so a future npm release
cannot silently turn an unreviewed lifecycle script into an installation step.
See the [npm install-script approval documentation](https://docs.npmjs.com/cli/v11/commands/npm-approve-scripts/)
for the upstream field semantics.

The authoritative review files are:

- `publication/dependency-install-script-allowlist.json`;
- `publication/dependency-advisory-decisions.json`;
- `publication/prompt62-dependency-audit.json`;
- `publication/sbom/node.cdx.json` and `publication/sbom/python.cdx.json`.

Accepted findings are not hidden. Each has an owner, reachability analysis,
exploit surface, fix status, compensating control and review date. The default
native and retained-reference Python locks currently have no known finding. The
optional SciPy 1.8.1 finding is retained temporarily because its affected
`Py_FindObjects` helper is not used by FORCE; changing SciPy requires the
independent LP and numerical regression gates.

## Checksums and signing

The beta does not claim signed provenance. Deterministic release builders write
SHA-256 values and SBOMs, and the release notes must publish those values next to
each asset. Signing is deferred until the repository has a protected release
workflow and a maintainer-controlled signing identity. At that point, signatures
will supplement rather than replace SHA-256 and SBOM evidence.

## Offline installation

The normal installer uses pinned locks and therefore needs access to PyPI and
npm. A fully offline wheelhouse is not shipped in this beta: Python wheels are
platform-specific, some solver/reference packages are optional, and mirroring
third-party files adds a separate licence and vulnerability-maintenance duty.
For an offline deployment, a maintainer should build a platform-scoped
wheelhouse on an online Windows/Python 3.10 machine, retain every upstream file
hash and licence, transfer it through an approved medium, and install with
`pip --no-index --find-links`. JavaScript packages require the same controlled
npm cache or internal registry process. Do not treat an arbitrary copied cache
as a FORCE-signed distribution.

The source code, CC0 synthetic pack and rights-cleared UK benchmark asset remain
separate products. No credential, npm token, GitHub token or private data object
belongs in an offline bundle or source archive.
