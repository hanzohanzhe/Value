# Study Trash and Preflight Documentation Design

## Scope

Add a recoverable lifecycle for saved Studies and make VALUE 101 explain what
Check readiness resolves. This change does not alter PSM, CEM, solver, data,
Study scientific contracts, model results or run clocks.

## Study lifecycle contract

- Every saved Study, including VALUE 101 Studies, uses the same trash rules.
- Moving a Study to trash moves the complete Study directory and every immutable
  revision. It never deletes a Data Pack, Module or Run.
- Active linked Runs (`queued`, `snapshotting`, `running`, or
  `cancel_requested`) block the operation.
- A Study with linked historical Runs requires the exact Study name as
  confirmation. A Study with no Runs uses ordinary confirmation.
- Historical Runs remain readable and are labelled `Source Study in trash`.
  Actions that create a new Run or Study from that source are disabled until the
  Study is restored.
- Trash entries are retained indefinitely in this version and expose Restore,
  but no permanent-delete action.
- A trashed Study ID remains reserved. Restore returns the original directory
  and revisions, then normal validation may mark the Study `Needs attention` if
  a declared Data Pack or Module is unavailable.
- Reset VALUE 101 uses the same trash record and movement service for teaching
  Studies and teaching Runs. Ordinary research records are untouched.
- Legacy `trash/value-101-reset/<timestamp>` entries remain readable without
  relocation or rewriting.
- The audit record stores deletion time, reason, original path, Study ID, Study
  name, revision identity and count, linked Run IDs/count, and recovery state.

## Product behaviour

- Saved Study cards expose a three-dot menu with `Move to trash`.
- A collapsed Trash section below Saved Studies lists newest first and provides
  Restore. Restore does not automatically select the Study.
- If the selected Study is moved, VALUE clears Study/Run selection, returns to
  Studies, and shows a success message.
- VALUE 101 Learn shows `Restore baseline` when the baseline exists in trash;
  it does not silently recreate it.

## Check readiness documentation and wording

- English and Chinese tutorials, the generated English guide, and the
  VALUE 101 to VALUE-UK guide explain the shared preflight steps.
- Single-node Studies validate and freeze their declared Data Pack, modules,
  parameters and clock. They do not resolve an internal network pack.
- Zonal Studies additionally resolve and verify one compatible signed network
  pack, its topology, ratings, demand allocation, mapping, identity and clock.
- Before a zonal preflight the UI says `Network pack: Check readiness to
  confirm`; after success it displays the exact pack ID followed by `verified`.
  A failure states the incompatible role and corrective action.
- `Resolved during preflight` means not yet confirmed. It never means missing,
  randomly selected, downloaded during execution or silently replaced by a
  copperplate fallback.

## Verification boundary

Use focused lifecycle/API tests, frontend lint/build or the narrowest existing
render check, documentation assertions, PDF generation and PDF text extraction.
Do not run annual, two-year, ten-year or complete Python suites.
