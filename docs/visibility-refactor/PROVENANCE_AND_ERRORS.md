# Provenance, errors and run-bundle validation

Every new completed run writes `provenance.json` at the run root. Failed new
runs write an explicitly incomplete provenance record; historical directories are
never backfilled or edited.

## Provenance summary

The completed-run schema is `gridform.run-provenance/v2` and records:

- run, project and Data Pack IDs plus their schema versions;
- every selected module ID, semantic/scientific version, contract, Python entry
  point, source SHA-256 and snapshotted-manifest SHA-256;
- Git commit and dirty flag when Git metadata is available, otherwise a stable
  reason code;
- the Python executable name, Python/platform identity and relevant scientific
  dependency versions;
- every Data Pack binding's declared checksum, format and byte count;
- complete effective scientific/runtime settings and independent hashes of both;
- the deterministic planning-draw algorithm and seed;
- initial state hash and an annual input/output state-hash chain;
- a relative-ID/checksum/size/schema index of immutable run artifacts.

Example abbreviated identity:

```json
{
  "schema_version": "gridform.run-provenance/v2",
  "completion": {"status": "completed"},
  "identity": {
    "run_id": "application-smoke",
    "project_id": "application-smoke",
    "data_pack_id": "uk-scheme-c-1000twh",
    "resolved_run_schema": "gridform.resolved-run/v2",
    "project_schema": "gridform.project/v1",
    "data_pack_schema": "gridform.data-pack/v1"
  },
  "randomness": {
    "planning_success_mode": "expected",
    "planning_seed": 0,
    "planning_draw_algorithm": "md5-prefix-mod-1000000/v1",
    "python_hash_seed": 0
  }
}
```

No environment-variable dump, diff content, secret, Data Pack absolute path or
Python installation path is copied into this record. The HTTP provenance endpoint
returns a curated subset and never returns an absolute workstation path.

## Stage evidence

`orchestrator-events.jsonl` uses `gridform.stage-event/v3`. Each record contains
the selected module ID/version/contract, input and output contract hashes,
run-relative artifact IDs, and measured duration. The bundle validator compares
planning-advance inputs and transition outputs to the annual state chain.

## Error taxonomy

| Public code | Category | Meaning |
| --- | --- | --- |
| `GF_CONTRACT_001` | contract | Module selection or typed input/output mismatch |
| `GF_DATA_001` | data | Missing/unreadable Data Pack binding |
| `GF_PARAMETER_001` | parameter | Invalid project scientific/runtime setting |
| `GF_COMPATIBILITY_001` | compatibility | Unsupported Python/model runtime |
| `GF_INVARIANT_001` | invariant | Year, capacity or scientific invariant failure |
| `GF_ARTIFACT_001` | artifact | Artifact write/validation failure |
| `GF_RUNTIME_001` | runtime | Unexpected execution failure at the runner boundary |

`status.json` contains only the stable public code, category and safe message.
The local `diagnostics/error.json` contains the exception type, original message
and traceback. The UI displays the stable code. Recoverable conditions use
`gridform.warning/v1` with code, category and `info`/`warning` severity.

Silent broad exception handlers were removed from the public status/evidence
paths. A corrupt optional module-progress file now produces
`GF_MODULE_EVIDENCE_READ_WARNING`; a corrupt pre-existing status while recording a
failure produces `GF_STATUS_READ_WARNING`. The outer API and runner catches remain
deliberate process boundaries and always record/return a structured failure.

## Validate a bundle

```powershell
py -3.10 -m gridform_core.bundle_validator .gridform/runs/<run-id>
```

The command checks indexed files and SHA-256 values, referenced manifest and
resolved-configuration artifacts, provenance schema, orchestrator event JSON and
annual state-chain continuity. It does not rerun the model. Exit code is zero only
for a valid bundle.

The integration test validates an untouched real two-period bundle, appends one
byte to a snapshotted module manifest, and proves the validator returns
`GF_BUNDLE_HASH_MISMATCH` for the corrupt copy.

