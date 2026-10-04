# Prompt 109 — VALUE 101 identity and public capability boundary

Status: implemented and bounded-regression tested on 24 August 2026.

Execute against the approved
[`VALUE 101 teaching redesign`](../../superpowers/specs/2026-08-24-value-101-teaching-redesign.md)
and its
[`implementation plan`](../../superpowers/plans/2026-08-24-value-101-teaching-redesign.md).
This prompt establishes product identity and registry visibility only. It does
not claim that the three-pack family, guided experiments, Windows pilot or
30-minute external-user gate is complete.

## Rollback point

- pre-change prototype commit: `1b3d576d19cc118b8bf1ef773c53147618ba35c8`;
- tag: `value-101-pre-prompt109-20260824`;
- design/plan commit retained immediately before it: `069a031`.

The checkpoint includes the existing Lesson 1 frontend, English handout and
transactional Windows-installer prototype. The retained Scheme C source and
accepted hashes were not edited.

## Implemented contract

1. The canonical teaching module is `gridform_core.value_101`.
2. The public identity is `VALUE 101 — a synthetic GB-style teaching system`.
3. The canonical Study is `value-101-baseline`, selecting
   `value-101-baseline-v1`, 2025–2026 and 48 half-hours per model year.
4. The Study uses the ordinary production PSM, storage-cost, investment,
   expansion-cap, planning and transition modules. No tutorial solver exists.
5. `GET /api/tutorials/value-101` is the only teaching descriptor route. The
   old Castle route returns 404; no compatibility alias was added.
6. The normal workspace registry excludes the experimental AC checker and its
   data extension. Developer tests must explicitly request
   `include_internal_experimental=True`.
7. AC implementation source remains available for internal direct tests, but
   its manifests live outside the ordinary manifest directories. The generated
   public module catalogue is rebuilt from the ordinary registry.

## Verification evidence

- Prompt 109 contract: 3/3 passed after an observed 3/3 red failure.
- Tutorial runtime: 7/7 passed.
- Staged copperplate: 12/12 passed.
- Internal AC feasibility: 7/7 passed through explicit internal activation.
- Contracts v2: 3/3 passed.
- Application service: 18 passed, 1 expected local-pack skip.
- Expanded Study/public-registry contract: 6/6 passed.
- Documentation consistency: 15/15 passed after regenerating the public module
  table.
- Retained Scheme C source/data manifest: 1/1 passed.

The local `py` launcher did not enumerate the installed Python 3.10 runtime.
Tests therefore used the existing CPython 3.10.11 executable at
`%LOCALAPPDATA%/Programs/Python/Python310/python.exe`. No dependency was
installed and no model code was changed to compensate for launcher discovery.

## Boundaries carried forward

- Prompt 110 must replace the still-installed Castle teaching pack with three
  deterministic VALUE 101 packs before the product can be packaged.
- Prompt 112 must remove remaining Castle and AC presentation code from release
  user surfaces.
- Prompt 116 owns the final clean public-text scan and installer rename.
- Direct internal AC tests do not establish a public AC capability.
