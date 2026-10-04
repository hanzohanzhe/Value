# CI and dependency policy

The Windows job is authoritative for the supported local product. It checks the
exact Python lock, source portability, retained-source hashes, contracts,
independent dispatch validation, synthetic data integration, external module
execution, frontend build and package contents. A portable-core job exercises
only components whose contracts do not require the private UK pack.

`package-lock.json` supplies npm integrity hashes. Python locks pin every accepted
runtime distribution; their installed versions are checked by
`scripts/verify_locks.py`. The beta still lacks a repository-owned signing key and
hash-locked Python wheelhouse, so signed/offline installation remains a release
gap rather than an implied guarantee.

SBOMs are generated from committed locks. The dependency audit is enforced on
ordinary branches as well as release tags: a known remotely exploitable
high/critical issue is blocking, and every lower-severity or build-only finding
requires a documented owner decision and expiry. No CI artifact may contain `.gridform`, UK
research files, local runs, absolute user paths, secrets or browser traces from a
successful test.

The retained Scheme C numerical gate requires its locally licensed data snapshot.
Public CI therefore runs preservation/contract checks but cannot claim the full
annual Scheme C numerical gate. That gate belongs to the local staged release
report until redistribution rights permit a CI fixture.
