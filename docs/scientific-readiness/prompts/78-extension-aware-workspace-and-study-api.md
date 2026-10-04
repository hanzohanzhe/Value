# Prompt 78 — Extension-aware workspace and Study API

Execute only after Prompt 77 is accepted. Read the frozen interaction contract,
Prompt 65 extension schemas, Prompt 73 application-entry contract,
`workspace_registry()`, project fingerprinting, preflight, snapshot and resume
identity code. Act as an API architect and reproducible-model configuration
engineer. Do not edit any PSM, CEM, hydrology or network equation.

## Objective

Make the ordinary browser backend expose and persist the same extension graph
that the application service already resolves. A Study created through the API
must be able to select an extension without manual file editing or a validation
bypass.

## Work

1. Add an additive, versioned workspace response containing the registered
   extension catalogue: ID, version, licence, namespace, maturity, provided and
   required capabilities, composed modules, data roles, parameters, artifacts,
   hooks, installation source and enabled state.
2. Expose all supported module slots from the registry, including optional
   `network_expansion`; do not maintain a second backend constant that can drift.
3. Extend project validation to pass `selected_extensions`,
   `extension_parameters`, available data roles and selected module capabilities
   into the one registry. Preserve the existing automatic storage-cost rule only
   for PSMs that require `storage.bid-cost-function`.
4. Save selected extensions, resolved extension parameters, explicit maturity
   acknowledgements and the graph preview in append-only project revisions.
   Unknown fields, capabilities, parameters, roles and module slots must fail
   closed with stable error codes.
5. Ensure fingerprints, immutable run snapshots, checkpoints, resume,
   provenance, exports and project reload bind to the same complete module and
   extension graph SHA-256.
6. Add a bounded endpoint that resolves a draft selection without saving it and
   returns required conditional roles, compatible modules, missing
   dependencies, maturity warnings, effective parameters and graph identity.
   It must execute the same validation functions as save/preflight.
7. Keep v2 single-node project JSON valid. An absent extension field means no
   extension; it must not auto-enable network or hydrology.

## Tests

Cover base single-node, DC plus network contract, AC feasibility plus both
network/AC data extensions, hydrology, DC plus transmission expansion, unknown
extension, missing role, missing solver, incompatible single-node/network
composition, extension parameter error, extension version upgrade and old
project reload. Assert identical graph hashes across preview, save, preflight,
snapshot and application invocation.

Mutation tests must fail if project validation drops extensions, ignores a
conditional role, recomputes a different graph or permits an unacknowledged
experimental method.

## Acceptance

The production API can save and preflight every supported Prompt 65–70 fixture
without direct filesystem editing. Existing Prompt 64 project revisions and
results remain byte/scientifically unchanged. No frontend change is accepted in
this prompt beyond API fixtures or generated types needed for Prompt 79.

