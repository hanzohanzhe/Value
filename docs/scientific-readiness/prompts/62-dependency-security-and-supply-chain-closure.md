# Prompt 62 — Dependency security and supply-chain closure

Execute from Prompt 59's canonical branch. Read Prompt 25, the locked Python/npm
files, CI policy, SBOM builder, Prompt 58 executable-module boundary, the private
upload audit and `SECURITY.md`. Act as a dependency, application-security and
release engineer.

## Objective

Resolve or explicitly time-bound every release-relevant dependency finding and
installation-script warning, then make the security decision reproducible in CI
without changing scientific numerics by accident.

## Non-duplication boundary

- Reuse the existing Python locks, `package-lock.json`, SBOM, doctor, package
  scanner and Windows/Linux CI. Do not introduce another package manager.
- Do not run `npm audit fix --force`, float dependencies or upgrade unrelated
  numerical packages as a batch.
- Do not claim that the in-process module installer is a sandbox. Strengthen its
  declared trust boundary only where tests justify it.
- Dependency-only work does not trigger ten-year runs unless a scientific
  implementation or numerical dependency changes.

## Implement

1. Re-run current npm and Python vulnerability audits with pinned audit-tool
   versions. Record advisory ID, affected package/path, runtime versus build/test
   reachability, exploit surface, fix availability and disposition.
2. Review every dependency install script. Create the smallest explicit allowlist
   with package, version, reason and expiry; block undeclared scripts in CI.
3. Upgrade one dependency group at a time. Regenerate only the authoritative
   lock, build/test after each group and retain before/after SBOM and licences.
4. Treat known remotely exploitable high/critical runtime findings as release
   blockers. For build-only findings, require a named owner, rationale, compensating
   control and review date; never silently accept them.
5. Audit Python extras independently so solver/reference/export dependencies do
   not expand the default attack surface. If SciPy/PuLP/CBC or a scientific
   numerical dependency changes, run its independent solver and numerical gates.
6. Add a confirmed private reporting contact and response expectations to
   `SECURITY.md`. Configure automated advisory checks without granting write
   access to model data or secrets.
7. Decide and document release checksums/signing and offline wheelhouse policy.
   If signing is deferred for beta, say so and publish reproducible SHA-256/SBOM
   evidence rather than implying signed provenance.

## Tests and acceptance

- No unaccepted high/critical runtime finding remains at the candidate date.
- Every install script and remaining advisory has a machine-readable decision.
- Locks recreate the approved environment and package/source scans pass.
- Frontend unit/E2E/build and complete Python tests pass on clean CI.
- Independent PSM tests pass if any numerical dependency changed.
- Retained Scheme C and accepted scientific implementation hashes remain stable,
  or the change-impact record escalates tests appropriately.

## Stop condition

Stop release rather than suppressing an advisory, disabling the audit, allowing
all install scripts or making an unvalidated numerical upgrade. Network access
and registry/package publication require explicit authorization.

## Deliverable

Provide the advisory ledger, allowScripts policy, lock/SBOM deltas, security
contact, signing/offline-install decision and release GO/NO-GO. Do not run annual
or ten-year models for build-only changes.
