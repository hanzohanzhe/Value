# VALUE Network Extensions architecture

## Separation of concerns

```text
Module registry        Data-pack registry
      │                       │
      └──────────┬────────────┘
                 ▼
          Research project
      module IDs + data pack +
        years + parameters
                 │
                 ▼
             Run snapshot
                 │
                 ▼
      Annual modular orchestrator
                 │
   PSM → investment → caps → pipeline
                 │
                 ▼
       next-year state and results
```

The data pack owns data. The module registry owns executable implementations.
The research project owns a reproducible selection. The run owns execution
evidence and results.

## VALUE preservation rule

The reference files `compat/case3.py` and `exact_run.py` are unchanged.
`compat/modular_case3.py` is a separate copy used for project composition.

The copied file replaces five direct call sites with injected calls:

1. PSM execution;
2. agent investment;
3. VRE expansion cap;
4. storage expansion cap;
5. planning pipeline.

The built-in implementations delegate to equations copied from VALUE, so the
reference source remains available for parity comparison.

## Runtime resolution

The project stores module IDs by slot:

```json
{
  "modules": {
    "psm": "value-bid-at-cost-psm",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy"
  }
}
```

`ModuleRegistry.resolve()` verifies both the ID and slot. The runner builds a
process-local runtime from those implementations and injects it before the
copied annual kernel is imported. Unknown, missing or wrong-kind selections are
rejected before execution.

Each call emits a JSON Lines event containing the year, module ID, module
version, action and relevant evidence. This proves that the selected stage was
actually invoked; merely displaying an ID in the UI is not sufficient.

## Reproducibility

Each run directory contains:

```text
status.json
project-snapshot.json
data-pack-snapshot.json
model.log
model-output/
  module-events.jsonl
  modular-run.json
  checkpoints/
  VALUE CSV and SQLite outputs
```

The snapshots prevent later edits to a project or data-pack manifest from
changing the interpretation of an existing result.

## Python environment

VALUE reference execution is pinned to Python 3.10. The launcher:

1. stops previously recorded VALUE PIDs;
2. locates Python 3.10;
3. verifies the interpreter version and scientific dependencies;
4. starts the API with that exact executable;
5. checks the API-reported runtime before opening the frontend.

This fixes the earlier stale-process failure where a Python 3.12 service
continued to own port 8766 while the launcher appeared to start another
backend.

## Database extension contract

```text
source database
  → connector
  → field and code mapping
  → unit/time normalisation
  → schema and relationship validation
  → immutable data-pack binding
```

Connectors may read CSV, Parquet, NetCDF, SQL or APIs. They must not add
organisation-specific database code to PSM or CEM modules.

A production connector should validate:

- required columns and data types;
- MW versus MWh/period semantics;
- timezone and 17,520-period alignment;
- unique asset/project identifiers;
- technology and planning-status code mappings;
- references between projects, regions and technologies;
- source version, licence and checksum.

## Model extension contract

New PSM or CEM implementations are registered as new IDs. They must not reuse an
existing VALUE ID.

Every implementation declares:

- module slot and version;
- required semantic inputs;
- produced outputs;
- parameter schema and defaults;
- units;
- state mutations;
- deterministic/random behaviour;
- regression fixtures.

A DC or AC network formulation is therefore a new `psm` implementation. A new
demand profile is normally a data adapter or demand-provider module. A new
investment or planning method fills only its corresponding CEM slot.

## Release gates

1. unit and contract tests;
2. frontend build and server-render test;
3. Python 3.10 initial-state integration test;
4. two-period module-evidence test;
5. complete 2025–2026 run;
6. retained-output numerical comparison.

A successful process is not automatically a numerically validated model.
