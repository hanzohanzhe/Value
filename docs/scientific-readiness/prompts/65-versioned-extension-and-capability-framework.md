# Prompt 65 — Versioned extension and capability framework

Execute only after Prompt 64 has established a canonical single-node beta. Read
the v2 contracts, one workspace registry, 25-role data catalogue, executable
adapters, project revisions, run snapshots, module conformance and Prompt 58
bundle installer. Act as a platform architect. Preserve all v2 Study behaviour
and do not add network or hydrology equations in this prompt.

## Objective

Make the documented third extension level—adding new model domains such as
hydrology or transmission—a real, versioned mechanism. A modeller must be able to
extend contracts, data requirements, parameters, run state and output artifacts
without editing FORCE core or creating an unregistered side path.

This complements, rather than replaces, the two existing levels:

1. replace one policy module within the existing v2 slots;
2. replace a complete PSM or CEM engine while keeping the v2 domain contract;
3. install an extension pack that declares additional capabilities and contract
   families, then select compatible engines and data.

## Non-duplication and compatibility boundary

- Extend `gridform.module/v2` and the one `workspace_registry()` resolution graph;
  do not create a second module registry, runner or project format.
- Reuse `force.module-bundle/v1` security, hashing, trust acknowledgement,
  transaction and provenance rules. An extension bundle may compose accepted
  module bundles; it must not invent a weaker ZIP installer.
- The existing 25 roles remain the complete base profile. Extra roles are
  conditional requirements activated by declared capabilities, never added as
  fake mandatory empty files to every UK Study.
- Existing v2 single-node projects, snapshots, checkpoints and result bundles
  must load and execute unchanged. No implicit migration may alter them.
- Namespaces owned by an extension must not collide with FORCE built-ins or other
  installed extensions.

## Contracts

1. Define `force.extension-bundle/v1` with ID, semantic version, licence,
   required FORCE/contract versions, provided/required capabilities, composed
   module IDs, data-role schemas, parameter schemas, state schemas, artifact
   schemas, migrations and exact member inventory.
2. Add capability negotiation to the existing resolved graph. Examples include
   `domain.single_node`, `domain.network.dc`, `domain.network.ac`,
   `resource.hydrology.run_of_river`, `resource.hydrology.reservoir`,
   `output.nodal_prices` and `cem.network_expansion`. Selection must fail before
   a run if providers, consumers and data cannot agree on one versioned graph.
3. Let modules declare a bounded JSON Schema for module-owned parameters,
   defaults, units, scientific descriptions, allowed ranges and advanced/basic
   visibility. Store resolved values and schema hashes in Study revisions and run
   snapshots. Never execute UI expressions or arbitrary validation code.
4. Let capabilities add conditional canonical data roles with file/media schema,
   unit/coordinate/time semantics, adapter contract, provenance/licence fields
   and validation rules. Display base and capability-specific readiness separately.
5. Add a namespaced extension-state container to `YearState` with declared owner,
   schema version, serialization, migration and lifecycle hook. Core modules may
   not inspect unknown state. Orphaned or incompatible state fails closed.
6. Add a namespaced artifact registry so extensions can publish typed files and
   summary fields without placing arbitrary messages on the main run screen.
   Every artifact records producer module, schema, source inputs and hashes.
7. Define explicit lifecycle hooks—preflight, initialize, before/after PSM,
   before/after CEM stages, transition and finalize—with immutable inputs and
   typed returns. Ordering and conflicts are resolved in the frozen module graph,
   not by import order.
8. Extend project revision, run snapshot, checkpoint, export/import and comparison
   identities to include the complete extension graph and schema hashes.

## Developer and user experience

- Generate Study forms from safe parameter schemas, grouped as basic or advanced,
  with units, validation and provenance. The frontend remains a client; backend
  contracts are authoritative.
- Show why a module is selectable or incompatible, which new data roles it
  activates and which outputs it will add.
- Extend the bilingual “Build your own model” 101 with minimal examples for all
  three levels, including one harmless toy extension with a conditional data role.
- Provide scaffold, validate, build and dry-run commands. Conformance and
  scientific validation remain visibly distinct.

## Tests and acceptance

1. Every existing v2 Study produces the same frozen graph, snapshot and scientific
   outputs when no extension is selected.
2. A toy extension installs transactionally, adds one conditional role and safe
   parameter form, persists namespaced state across two years and publishes a
   typed artifact through the normal run path.
3. Missing capability, incompatible version, namespace collision, cyclic hook
   order, invalid parameter schema, orphaned state and undeclared artifact fail
   before execution with stable errors.
4. Disable/uninstall rules protect saved Studies, checkpoints and historical runs
   exactly as Prompt 58 protects ordinary modules.
5. Malicious schemas, traversal, oversized bundles and unlisted executable bytes
   fail under the existing installer security boundary.
6. Project fingerprints and resume identities change when and only when the
   selected extension graph, parameters, data or implementation changes.
7. Python, frontend, browser, source-release and generated-document tests pass;
   no annual or ten-year scientific run is required for the toy extension.

## Stop conditions

Stop if implementation requires editing retained Scheme C, adding a second
registry/orchestrator, silently migrating v2 projects, executing frontend-provided
code or treating an extension's data as optional after its capability is selected.

## Deliverables

- versioned extension/capability contracts and one-registry resolution;
- conditional data roles, safe parameter schemas, state/artifact namespaces and
  deterministic lifecycle hooks;
- transactional installer integration and toy reference extension;
- three-level bilingual developer documentation and conformance kit;
- compatibility, security, migration and two-year state-persistence evidence.
