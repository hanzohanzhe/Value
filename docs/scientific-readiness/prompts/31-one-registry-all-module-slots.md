# Prompt 31 — One workspace registry for every executable module slot

Continue only after Prompt 30 is accepted. Read visibility Prompt 02 and
scientific Prompts 04 and 12. Audit `workspace_registry()`, `scheme_c_registry()`,
manifest discovery, application resolution and the special external
storage-cost fallback. Act as the public SDK and plugin-runtime owner.

## Objective

Make one manifest-derived workspace registry the source of truth for resolution
of PSM, storage-cost, VRE-cap, storage-cap, investment, planning-pipeline and state
transition implementations. Preserve Scheme C adapters as registered modules, not
as a private hard-coded catalogue.

## Non-duplication boundary

- Contracts v2, manifest schema, conformance tests and the frontend catalogue
  already exist. Fix resolution and invocation; do not add a parallel registry or
  new module contract family.
- The current external storage-cost fallback proves the desired discovery path.
  Generalize the registry architecture, but do not force a v2 module through an
  incompatible legacy `*args/**kwargs` hook.
- Do not change module science, parameter semantics or lifecycle order.
- Browser uploads remain data-only. Executable modules require explicit local
  installation and conformance, as Prompt 04 specifies.

## Implement

1. Resolve the complete project composition once from `workspace_registry()`
   before enqueue/snapshot. Persist exact manifest, implementation entry point,
   distribution/source hash, slot, contract and capability closure.
2. Remove the production `scheme_c_registry()` hard-coded selection path. Register
   built-in Scheme C implementations through the same manifests and workspace
   resolver used for external modules.
3. Remove the storage-cost-only fallback branch. All slots use the same resolution
   service and error taxonomy. A missing, duplicate, wrong-slot or incompatible
   module fails before model output.
4. Where the reference Scheme C runner needs a legacy hook, provide an explicit
   internal bridge selected by capability and version. It may adapt an accepted
   built-in for comparison, but must never make an arbitrary conformant v2 module
   appear legacy-compatible. Native production invocation remains through v2.
5. Make the API/frontend catalogue expose executable status for the selected
   runtime path, including why a module is unavailable for a reference-only
   comparison. Do not label manifest discovery alone as executable proof.
6. Record one resolution graph in the input snapshot and require the same graph on
   resume. Eliminate later per-slot re-resolution.

## Tests and acceptance

- Install one distinctive external fixture for every slot. A real website-worker
  run resolves the exact fixture from the workspace registry and its output
  changes the next typed stage and final bundle.
- Repeat the mutation one slot at a time, including the two planning phases and
  state transition. Storage cost is no longer a special discovery case.
- Duplicate ID, incompatible capability, wrong contract, changed source hash and
  missing distribution fail before the first scientific stage with module/slot
  identity.
- Frontend catalogue, preflight, snapshot and worker report the same resolved
  module graph.
- No production source constructs a second built-in registry or silently replaces
  an external module with Scheme C.
- Retained-source hashes and accepted built-in results pass.

## Stop condition

If any project-selected slot is resolved from a different registry or replaced by
a compatibility default at execution time, keep the real-module gate failed.

## Deliverable

Provide the before/after resolution graph, removed special cases, all-slot external
execution proof, capability failures, snapshot/resume proof and remaining
reference-only bridges.
