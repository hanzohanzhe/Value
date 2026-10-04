# Production annual orchestrator v2

The local website and CLI call only `gridform_core.application.run_project_application`.
That service validates manifests and parameters, adds the fixed Scheme C state
transition, and publishes this public lifecycle for each year:

```text
YearState(y)
  -> planning.advance_year        # commissions projects before dispatch
  -> psm.run
  -> storage_cap.evaluate
  -> vre_cap.evaluate
  -> investment.decide(headroom)  # both named caps are inputs
  -> planning.admit_projects      # proposals join after investment
  -> state_transition.apply
  -> YearState(y + 1)
```

The orchestrator refuses an implementation whose ID or version differs from the
resolved project, validates stage years and non-negative capacities, writes a
state hash on every stage event, and writes a checkpoint after every transition.
It has no fallback module selection.

## Scheme C compatibility boundary

Numerical parity currently requires the copied Scheme C annual compatibility
session because its scientific state consists of generator/battery objects whose
exact investment and storage behaviour has not yet been rewritten as native v2
state. The application resolves the manifests first, and the copied session calls
the exact project-selected PSM, investment, planning and expansion wrappers. It is
not the untouched reference copy and it cannot silently substitute another module.
Its outputs are materialised through the typed v2 modules and
`AnnualModelOrchestratorV2` into:

- `orchestrator-events.jsonl` with module identity/version and input/output hashes;
- `year-results-v2.json` with public contracts only;
- `checkpoints-v2/state-YYYY.json`;
- `resolved-run.json`.
- `parity/stage-parity.json`, which compares the scientific-session artifacts,
  durable ledgers and public contracts.

The direct retained runner remains available only through explicit comparison
commands. `backend/model_runner.py` imports only the application service. The
remaining compatibility boundary is explicitly named in the application result;
there is no silent switch to a simplified demo model. Native v2 scientific state
is a future internal refactor, not a claim of this release.
