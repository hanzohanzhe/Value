# DATA-01 — Lifecycle and service contracts

Execute only after the approved Data Workbench design is committed. Act as a
data-platform architect. This prompt creates infrastructure contracts; it does
not fetch public data or alter model mathematics.

## Objective

Create the versioned lifecycle objects, storage ports and service boundary for
`discover -> fetch -> compile -> validate -> promote`, together with an isolated
local state layout and a compatibility boundary for Prompt 98.

## Required work

1. Add `gridform_core.data_workbench` with immutable, JSON-serializable models
   for `SourceDefinition`, `SourceRevision`, `RawObjectReceipt`,
   `BuildManifest`, `CandidatePack`, `ValidationReport`, `PromotionRequest` and
   `SignedBundleReceipt`.
2. Add the `force.data-workbench-api/v1` request and response envelope and
   protocols for `SourceRegistry`, `ObjectStore`, `JobStore`, `ApprovalStore`
   and `DataWorkbenchService`.
3. Resolve the workbench state root from the existing local application state;
   never derive it from the process working directory or expose it in DTOs.
4. Define canonical JSON and scientific-content hashing. Retrieval and approval
   timestamps must not change Candidate identity.
5. Retain the public functions in `gridform_core.gb_zonal_pack_builder`; document
   the facade boundary without moving Prompt 98 behaviour prematurely.
6. Generate an initial contract reference document and update the DATA gap
   matrix with observed evidence only.

## Acceptance gate

- Round-trip tests cover every lifecycle object and reject unknown schema
  versions and invalid status transitions.
- Identical scientific content with different timestamps has the same
  Candidate ID.
- Public DTOs contain no absolute local path.
- Existing Prompt 96–98 tests and retained-source hash tests still pass.
- No network call, source download or model execution is introduced.

## Stop conditions

Stop on a proposed second network schema, a second installed-pack registry,
global mutable configuration, or an API that exposes filesystem paths.

## Deliverables

- lifecycle contracts and protocols;
- local state-layout resolver;
- contract tests and generated reference;
- Prompt 98 compatibility note;
- DATA-01 gate record and commit.

