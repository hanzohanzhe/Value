# Prompt 111: auditable VALUE 101 lifecycle

## Purpose

Give the guided course an explicit local identity without creating a second
kind of Study or Run. VALUE 101 continues to use ordinary immutable Study
revisions, ordinary run snapshots and the production PSM/CEM orchestrator.

## Origin contract

Teaching-created Studies and Runs carry this extension:

```json
{
  "extensions": {
    "value_101": {
      "origin": "guided-course",
      "course_revision": "value-101/v1",
      "variant_kind": "baseline",
      "parent_project_id": null,
      "changed_dimensions": []
    }
  }
}
```

`variant_kind` may be `baseline`, `data`, `storage` or `network`. The v1-to-v2
parser now preserves an explicit `extensions` object rather than nesting or
discarding it. Scientific fingerprints remain based on the selected data,
modules, parameters and execution contracts; the course label is audit
metadata, not a hidden scientific input.

## Controlled lifecycle APIs

- `POST /api/tutorials/value-101/studies` creates the canonical baseline Study
  but does not launch a Run.
- `POST /api/tutorials/value-101/studies/{id}/clone-data` changes only the data
  pack and returns a leaf-path identity diff.
- `POST /api/tutorials/value-101/studies/{id}/clone-storage` changes only
  `modules.storage_cost` and returns the same audit form.
- `GET /api/tutorials/value-101/completion-report` returns local Study and Run
  identities and statuses. It uploads no telemetry.
- `POST /api/tutorials/value-101/reset` requires `{ "confirm": true }`.

Run status records inherit the same explicit origin. Reset uses only that
metadata; it never searches names or IDs for a `value-101` substring. Active
teaching Runs block reset. Completed teaching Studies and Runs are moved into a
timestamped local trash directory, making the reset recoverable. Data packs,
installed modules, ordinary research Studies and ordinary Runs are untouched.
The response tells the browser to remove `value.101.progress.v1` locally.

## TDD evidence

The first lifecycle test failed because `gridform_core.value_101_lifecycle`
did not exist. The accepted focused gate then passed 4/4 tests, covering:

- v1-to-v2 origin preservation;
- exact one-dimensional data and storage clones;
- name-substring false-positive protection;
- create-without-run, clone, report, confirmation refusal and scoped reset over
  the loopback HTTP service.

Affected revision, VALUE 101 identity and application-service regressions also
passed: 2/2, 3/3 and 18/18 with one expected local-pack skip.
