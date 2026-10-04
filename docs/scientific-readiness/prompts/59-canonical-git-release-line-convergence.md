# Prompt 59 — Canonical Git release-line convergence

Execute after Prompt 58. Read `POST_58_ALIGNMENT_PLAN.md`, `GIT_SNAPSHOT_POLICY.md`,
`source-release-manifest.json`, the Prompt 50 scan and the private GitHub upload
report. Act as a release engineer. Preserve every current worktree and retained
Scheme C file; do not delete or overwrite `yue-d`, the standalone `FORCE` demo
folder, snapshots or historical evidence.

## Objective

Establish one canonical Git working tree and branch for all subsequent FORCE
work. Reconcile the currently edited source, the standalone demo copy and the
last CI-validated private GitHub commit without losing either side or treating a
folder copy as a Git snapshot.

## Non-duplication boundary

- Reuse Prompt 50's allowlisted source product, package boundaries and scanner.
- Reuse the existing private `hanzohanzhe/FORCE` repository and its accepted
  history; do not create another repository with the same purpose.
- Do not rebuild UK data, rerun scientific scenarios or redesign Git policy.
- Do not use `git add .`, force-push, history rewriting or destructive reset.
- When publishing, use the authenticated GitHub connector/API required by
  `AGENTS.md`, not device-code login or an ad-hoc local push.

## Implement

1. Create an immutable pre-convergence archive and machine-readable inventory of
   every current release member, Git status, source SHA-256 and retained-source
   hash. Verify the archive can be read.
2. Fetch the private repository identity and validated base commit. If it cannot
   be read with the configured connector, stop before publication and report the
   missing authority; local file comparison is not proof of remote state.
3. Create a normal clone/worktree from the private repository. Compare the
   allowlisted tree with the current source by relative path and SHA-256. Classify
   files as identical, local-only new, remote-only new or conflicting.
4. Import intended current changes on a new branch using the allowlist. Keep UK
   data, `.gridform`, outputs, dependencies, build products and snapshots out of
   Git. Preserve authored history and do not silently choose a conflict side.
5. Ensure the new Build Your Own Model 101 documents, Prompt 56-58 work and this
   post-58 plan are included. Generate a release-member manifest tied to the
   resulting tree SHA.
6. Run source/path/credential/package scans and the bounded tests required by the
   actual change-impact record. Commit only after all intended members are
   tracked and no forbidden member is staged.
7. Publish the branch through the GitHub API and require CI. Record commit, tree,
   workflow and source-archive hashes. Do not merge to the default branch until
   Prompt 64.
8. Mark the standalone demo folder as a generated install/demo artifact in the
   documentation; it must no longer be described as the authoritative source.

## Tests and acceptance

- Exactly one documented canonical Git working tree is used for future changes.
- The source scanner reports zero untracked allowlisted release members and zero
  forbidden members from a fresh clone of the branch.
- Current and remote-only changes are reconciled explicitly; no file disappears
  without a recorded disposition.
- Retained Scheme C hashes are unchanged.
- The Build Your Own Model 101 files resolve from the candidate branch.
- CI status, commit SHA, tree SHA and source ZIP SHA-256 are machine-readable.

## Stop condition

Stop rather than guessing if the remote cannot be read, the base commit is
ambiguous, a conflict affects scientific code/data, or a release member has
unknown origin. Do not declare convergence from the current dirty worktree.

## Deliverable

Provide the convergence inventory, path/branch decision, conflict dispositions,
candidate commit and CI evidence. This prompt changes release state, not the
scientific baseline, so it must not launch annual or ten-year runs.
