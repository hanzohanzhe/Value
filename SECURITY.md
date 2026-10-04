# Security policy

FORCE is a loopback-only local research application. Report suspected path
traversal, unsafe archive import, checkpoint code execution, credential exposure
or unintended network binding privately to project owner Hanzhe Xing through
the repository's [private security-advisory form](https://github.com/hanzohanzhe/FORCE/security/advisories/new).
Do not open a public issue containing exploit details.

The maintainer aims to acknowledge a report within five working days, complete
initial severity and reachability triage within ten working days, and provide a
status update at least every fourteen days until resolution. A coordinated
disclosure date will be agreed with the reporter. These are response targets,
not a promise that every scientific or availability defect is a security issue.

Imported run bundles are data only. Python, scripts, native binaries and pickle
checkpoints are prohibited in portable bundles. Legacy pickle checkpoints are
trusted-local compatibility artifacts and must never be imported from shared
archives.

External model-module ZIPs contain executable Python. Their conformance checks
do not provide an operating-system sandbox; install only code whose source and
publisher you trust. Data bundles are governed by a separate non-executable
contract and reject Python, scripts, native binaries, links and nested archives.

The beta is distributed with deterministic source/data archive SHA-256 values
and CycloneDX-style SBOMs. It is not cryptographically signed. Verify published
hashes before offline transfer. See `docs/SECURITY_AND_SUPPLY_CHAIN.md` for the
dependency, install-script, offline-wheelhouse and signing decisions.
