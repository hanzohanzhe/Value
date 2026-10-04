# GridForm visibility refactor package

This package is the implementation brief for making the public GridForm model
contracts identical to the path executed by the local website. It is deliberately
separate from the retained Scheme C reference implementation.

Start with [ARCHITECTURE_PLAN.md](ARCHITECTURE_PLAN.md). It contains the audited
current call path, the visibility gaps, the target annual lifecycle, artifact
schemas, parameter policy, and release gates.

The files under `prompts/` are ordered implementation tasks. Give one prompt at a
time to Codex, in numeric order. A later prompt may rely only on the accepted
output and tests of earlier prompts.

## Non-negotiable preservation boundary

No implementation task may edit or regenerate these retained reference files:

- `gridform_core/builtin/scheme_c_1000twh/compat/case3.py`
- `gridform_core/builtin/scheme_c_1000twh/exact_run.py`
- `gridform_core/builtin/scheme_c_1000twh/AUTHORITATIVE_SOURCE.json`
- files in the imported `uk-scheme-c-1000twh` data pack
- retained reference fixtures or historical run outputs

New adapters, contracts and extracted implementations must be added beside the
reference files. Numerical changes are not allowed to hide inside an architecture
refactor. Any intended scientific change requires a new module ID, version and
research project.

## Prompt sequence

1. [Freeze baseline and boundaries](prompts/01-freeze-baseline-and-boundaries.md)
2. [Contracts v2 and module manifests](prompts/02-contracts-v2-and-module-manifests.md)
3. [Named Scheme C results](prompts/03-named-scheme-c-results.md)
4. [Planning-pipeline ledger](prompts/04-planning-pipeline-ledger.md)
5. [Parameter registry and advanced settings](prompts/05-parameter-registry-and-advanced-settings.md)
6. [Unified production orchestrator](prompts/06-unified-production-orchestrator.md)
7. [Fast market ledger](prompts/07-fast-market-ledger.md)
8. [Run API and frontend visibility](prompts/08-run-api-and-frontend-visibility.md)
9. [Provenance, errors and reproducibility](prompts/09-provenance-errors-and-reproducibility.md)
10. [Parity, benchmarks and cutover](prompts/10-parity-benchmarks-and-cutover.md)

Do not skip the first prompt. The existing worktree contains research changes and
the refactor must first establish read-only hashes and parity baselines.
