# Post-Prompt-28 compatibility remediation map

This map was written after reading the completed visibility prompts and scientific
Prompts 01-28, then inspecting the current 0.5.0-beta.1 production call paths. It
does not introduce a replacement architecture. Prompts 29-34 close acceptance
conditions that earlier prompts specified but the implementation has not yet met.

## Why these are new numbered prompts rather than duplicate designs

| Observed current gap | Existing prompt that already defined the target | Accepted work to preserve | Delta prompt |
| --- | --- | --- | --- |
| Release scan reports `load_mechanism_costs.py` because `year:\\n` resembles `r:\\`, while `config.py` has two real `E:` defaults | 24, 25, 28 | Rights inventory, locks, installer, source preservation, release scan | 29 corrects evidence/scanner and builds a source-hashed portable runtime overlay |
| Native/public stages still depend on mutable `compat.config`, environment, current directory and three fixed legacy filenames | visibility 09; scientific 13, 14 | Frozen snapshots, canonical roles, executable adapters, provenance | 30 adds one run-scoped context and confines legacy mutations without redesigning adapters |
| Scheme C uses a private hard-coded registry; only external storage cost falls back to the workspace registry | visibility 02; scientific 04, 12 | Manifest v2, catalogue, conformance kit, project revisions | 31 makes the existing workspace registry authoritative for every slot |
| Website `scheme-c-psm` runs the whole copied annual kernel and then binds `SchemeCReplayData` into v2 | visibility 06, 10; scientific 12 | AnnualModelOrchestratorV2, ledgers, adapters, reference runner, typed contracts | 32 completes Prompt 12's failed cutover and keeps replay/reference outside production |
| Compatibility kernel, older `psm.py` adapter and v2 replay definition share an ambiguous Scheme C PSM identity | visibility 02, 06; scientific 12, 27 | Manifest/versioning, legacy readers, mathematical reference | 33 consolidates identity and deprecates routes after the live cutover, without deleting history |
| Python 3.10 reference parity and native-runtime portability are conflated | 25, 27, 28 | Lock groups, doctor, installer, CI and bounded claims | 34 separates capabilities, validates claimed native versions and reruns existing release gates |

## Ordered execution and dependency rule

Execute 29, 30, 31, 32, 33 and 34 in order. Prompt 32 is the scientific and
architectural cutover; do not execute Prompt 33 before it returns GO. Prompt 34 may
hand control back to Prompt 28 only after all short prerequisites pass.

Current execution ledger: Prompts 29, 30 and 31 are accepted with evidence in
`publication/prompt29-compatibility-path-report.md` and
`publication/prompt30-run-context-report.md`, and
`publication/prompt31-workspace-registry-report.md`. Prompts 32 and 33 are also
accepted in `publication/prompt32-live-scheme-c-cutover-report.md` and
`publication/prompt33-psm-entrypoint-report.md`. Prompt 34 is executed and reported
in `publication/prompt34-runtime-and-release-gate-report.md`; its packaging and
runtime deltas are closed, while Prompt 17B stops the integrated release gate.

No prompt may edit retained Scheme C source, the installed UK pack, historical
runs or accepted fixtures to obtain parity. A deterministic runtime overlay,
narrow adapter or new native module belongs outside the retained tree and must
record both retained and generated hashes.

## Explicitly out of scope

These prompts do not reopen completed work on storage-cost equations, planning
semantics, cost/carbon ledgers, weather/demand ensembles, lifecycle controls,
results dashboards, data licensing or the perfect-foresight formulation. They may
rerun those tests because execution routing changes, but may alter their science
only through a separately approved research change.
