# Prompt 09 — Provenance, explicit errors and reproducible run bundles

Continue from accepted Prompts 01-08. Act as a scientific reproducibility and
observability engineer.

## Objective

Make each run self-identifying and replace silent failure paths with typed errors or
recorded warnings. A future user must be able to determine code, data, parameters,
environment, seed and state transitions from the run directory.

## Mandatory constraints

- Do not expose secrets, user environment contents or unrelated filesystem paths.
- Do not turn recoverable data-quality warnings into arbitrary model failure; define
  severity and reason codes.
- Do not retain broad `except Exception: pass` in core market, planning, state or
  artifact paths.
- Do not modify historical run directories in place.

## Work

1. Write `provenance.json` containing:
   - run/project/data-pack IDs and schema versions;
   - module IDs, versions, entry points and source hashes;
   - Git commit when available plus dirty-state indication without copying diffs;
   - Python executable/version and relevant dependency versions;
   - data binding hashes;
   - complete resolved scientific parameters and runtime options by reference/hash;
   - random algorithms/seeds;
   - initial state hash and annual state hashes.
2. Snapshot all selected module manifests.
3. Enhance module/stage events with contract versions, input/output state hashes,
   artifact IDs and duration.
4. Define typed exception categories for contract, data, parameter, compatibility,
   invariant, artifact and runtime failures.
5. Audit broad exception handlers. Replace silent passes in core paths with a typed
   failure or structured warning event. Keep narrowly justified UI/log cleanup
   exceptions documented.
6. Make `status.json` expose a concise public error with a stable code; retain the
   full traceback in a local diagnostic artifact.
7. Add a run-bundle validator that checks referenced files, hashes, schemas and
   annual state-chain continuity without rerunning the model.

## Tests

- Provenance completeness and hash validation.
- Dirty/unavailable Git metadata graceful handling.
- Error-code propagation from model runner to API/UI.
- Run-bundle validation success and intentional corruption failures.
- No-secret/no-absolute-path response tests.
- Source scan for prohibited silent exceptions in declared core files.
- Retained-source hash test.

## Deliverable

Provide a sample provenance summary, error taxonomy, removed silent failures and
bundle-validation results.
