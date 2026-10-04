# Data Workbench contract v1

The local CLI, HTTP API and future hosted client use
`force.data-workbench-api/v1`.

The lifecycle is strictly ordered:

`SourceDefinition → SourceRevision → RawObjectReceipt → BuildManifest → CandidatePack → SignedBundleReceipt`.

Public objects use identifiers and content-addressed object keys. They reject
absolute filesystem paths. Candidate scientific identity excludes only declared
observation, retrieval and approval timestamps.

The service exposes `discover`, `fetch`, `compile`, `validate` and `promote`.
Deployment details are isolated behind `SourceRegistry`, `ObjectStore`,
`JobStore` and `ApprovalStore`.

