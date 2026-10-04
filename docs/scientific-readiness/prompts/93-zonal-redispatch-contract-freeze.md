# Prompt 93 — Zonal redispatch contract freeze and rollback identity

Execute after Prompt 92. Read the approved design at
`docs/superpowers/specs/2026-08-21-zonal-redispatch-network-design.md`, Prompts
65–70 and 77–84, the current module/extension registry, release-gap matrix and
retained-source hash tests. Act as release architect. Do not change a scientific
equation in this prompt.

## Objective

Freeze the accepted copperplate/teaching candidate and define a non-overlapping
Prompt 93–106 network workstream. Record which existing optional components are
reused, superseded or withheld from the selectable product.

## Required work

1. Require a clean worktree. Create branch
   `codex/zonal-redispatch-prompt93-106` in an isolated worktree and annotated tag
   `pre-zonal-redispatch-prompt93-20260821` at the Prompt 92 source identity.
2. Record commit, branch, Python/frontend locks, source manifest SHA-256, retained
   Scheme C hash result and focused baseline test results in
   `publication/prompt93-pre-change-snapshot.json`.
3. Add a supersession matrix:
   - Prompt 67 network contracts remain reusable generic infrastructure;
   - Prompt 68 perfect-foresight DC-OPF remains a separate benchmark;
   - Prompt 69 AC feasibility remains experimental;
   - Prompt 70 contract types remain developer-facing, but its bundled reference
     implementation must not be selectable in the fixed-network release;
   - Prompt 83 read-only artifact patterns are reused, not its DC/expansion labels.
4. Pin the literal schema IDs, module IDs, data roles, result definitions and
   prompt dependencies used by Prompts 94–106.
5. Update the prompt index and release-gap matrix with status `planned`, not
   `implemented` or `accepted`.

## Acceptance

- The tag resolves to the exact pre-change commit and retained Scheme C hashes pass.
- Old single-node, Castle 101, DC-reference and historical Prompt 70 artifacts
  remain readable.
- No executable source, manifest status or model result changes in this prompt.
- `git diff --check`, prompt-index consistency and generated-doc consistency pass.

## Stop conditions

Stop if the worktree is dirty, the rollback identity cannot be recreated, or the
plan requires deleting historical Prompt 68/70 evidence.

## Deliverables

- Git rollback tag/branch;
- machine-readable snapshot and supersession matrix;
- indexed Prompt 93–106 workstream contract.
