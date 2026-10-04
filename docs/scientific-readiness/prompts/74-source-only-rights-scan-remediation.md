# Prompt 74 — Source-only rights-scan remediation

Opened by the Prompt 71 clean-clone gate. The UK benchmark pack is an explicit,
gitignored, separately distributed release asset. A source-only checkout therefore
does not contain its manifest. `scripts/release_scan.py` nevertheless attempted to
open that manifest unconditionally and crashed with `FileNotFoundError`.

Preserve the strict per-object verification whenever the separate asset is
installed. When it is absent, record `NOT_INSTALLED_SEPARATE_ASSET` without
claiming that its objects were verified and without treating absence as source-code
corruption. Add a regression fixture for both boundaries and rerun the rights,
source-release, package and complete Python gates. Do not add UK payload objects to
the source tree, wheel, sdist or synthetic CI pack. The scanner must also ignore
the repository-local `.venv`, which is installation state rather than a release
member; scanning dependency DLLs as source files creates false secret and size
findings.
