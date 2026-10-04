# Git snapshot policy

Git is the authoritative version and rollback system for FORCE.

## Required workflow

- Every accepted software state is recorded as a Git commit.
- A release, scientific baseline or pre-change rollback point receives an
  annotated, immutable tag.
- Work in progress uses a branch; it is merged only after the relevant tests
  pass.
- Run declarations record the source commit and, when applicable, the release
  tag.
- Historical tags are never moved, overwritten or reused.
- Large datasets remain separate versioned release assets. Their release tag,
  byte count and SHA-256 are recorded by the corresponding source version.
- A ZIP may be created as an offline disaster-recovery copy, but it is not the
  version identity and never replaces the Git commit/tag.

## Suggested tag names

- Software release: `force-vX.Y.Z`
- Pre-change rollback point: `force-pre-prompt-NN-YYYYMMDD`
- Scientific baseline: `force-baseline-description-YYYYMMDD`
- Original Scheme C baseline: `scheme-c-1000twh-2026-07-18_19`

Before tagging, require a clean worktree, record the test evidence, and confirm
that retained historical sources and data-asset hashes are unchanged.
