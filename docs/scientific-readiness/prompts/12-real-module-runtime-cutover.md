# Prompt 12 — Replace replay and hard-coded selection with real module execution

Continue from accepted Prompt 11. Read visibility Prompts 02, 06 and 10 and
scientific Prompt 04 before editing. Audit `gridform_core/application.py`, the
copied Scheme C module registry, backend runner and every production entry point.
Act as the runtime architect.

## Objective

Make the public website and CLI execute the project-selected PSM, investment,
VRE-cap, storage-cap, planning-pipeline and storage-cost implementations through
their declared v2 contracts. A copied monolithic kernel followed by replay is a
compatibility/reference path, not a modular production path.

## Non-duplication boundary

- The contracts, manifests, catalogue and conformance command already exist; fix
  their actual runtime use rather than defining a third contract system.
- Preserve the accepted annual lifecycle and all retained files.
- Do not claim success from spy metadata alone: selected code must affect typed
  downstream values.

## Implement

1. Produce a call-path audit identifying every replay object, whole-kernel call,
   hard-coded built-in lookup and silent fallback still reachable from website,
   CLI or backend worker.
2. Refactor the public application service so it owns the annual loop and calls
   each resolved v2 module directly. Built-in Scheme C stages may be narrow
   adapters around copied functions, but no adapter may execute an entire year and
   replay the answer across nominal stages.
3. Resolve every slot from the same project revision and registry. Remove
   per-slot hard-coded selection from production. If a selected module cannot load
   or execute, fail before scientific output; never substitute Scheme C silently.
4. Keep the old whole-kernel path under an explicitly named reference-comparison
   command. Its artifacts must be labelled `reference_compatibility`, not modular.
5. Hash the exact external implementation source/package resolved for a run and
   store it with manifest ID/version. Refuse an unversioned source change on resume.
6. Add a minimal external fixture implementation for every slot. Each fixture must
   make a distinctive, valid output change observable by the next stage and final
   bundle. Include a two-phase planning fixture.
7. Replace any UI or README statement that says all modules are executable unless
   the production-path proof below passes.

## Tests and acceptance

- A call-order/invocation test proves each selected external fixture is called by
  the same application service used by the backend worker.
- Mutation tests replace one slot at a time and prove its output reaches the next
  contract and changes the expected final field.
- A fixture that raises, returns the wrong type or changes after checkpoint fails
  with the correct module/stage identity and never falls back.
- No production source imports or constructs a replay object; enforce with a
  focused source scan and allowlist for reference tests only.
- Run two periods, one full year and a 2025-2026 transition through the new path.
  Compare stage by stage with the copied Scheme C compatibility path without
  weakening tolerances.
- Retained-source hashes pass.

## Stop condition

If parity diverges, keep the last accepted production path enabled, identify the
first divergent typed stage and leave the cutover `NO-GO`. Do not restore a hidden
replay path to make the test green.

## Deliverable

Provide old and new call graphs, a per-slot execution proof, remaining compatibility
adapters, first-divergence report if any, and the explicit cutover decision.

