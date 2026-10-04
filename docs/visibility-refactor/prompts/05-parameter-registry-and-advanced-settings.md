# Prompt 05 — Parameter registry and advanced settings

Continue from accepted Prompts 01-04. Act as a scientific configuration architect.
Read the environment/global-config inventory and the parameter policy in the
architecture plan.

## Objective

Classify every effective assumption as fixed, Data Pack-bound, user-editable
scientific, or runtime/output. Resolve one complete typed parameter set before a
run and remove scientific choices from hidden environment reads.

## Mandatory constraints

- Preserve current effective defaults so existing verified projects retain their
  results.
- Fixed Scheme C assumptions are documented and snapshotted, not casually exposed
  as sliders.
- Data Pack values remain versioned data; a project override must never silently
  overwrite the source without provenance.
- Environment variables may remain only for launcher/process mechanics during this
  migration and must not be the primary scientific API.

## Work

1. Produce a complete parameter inventory with current source, effective default,
   unit, scientific effect and target category.
2. Implement one parameter registry/schema containing type, allowed values,
   min/max, unit, visibility, owner module and precedence.
3. Implement a resolver with explicit precedence, for example:
   module fixed assumption -> Data Pack value -> project override, where allowed.
   Reject overrides of fixed fields.
4. Split resolved values into `scientific_parameters` and `runtime_options`.
5. Write the complete effective configuration to `resolved-run.json` before model
   execution.
6. Pass typed parameter objects to modules. Introduce compatibility translation at
   the Scheme C adapter boundary for legacy globals/environment variables; do not
   let new modules read them directly.
7. Add advanced-setting API metadata and validation. Include planning success mode,
   seed, uncertain projects, zombie rules, planning horizon/timing controls, VRE and
   storage cap fractions, supported storage-credit method, scenario and trace level.
8. Keep the large virtual storage pool, single-node topology, half-hour/full-year
   clock and bid-at-cost/no-commitment assumptions fixed for this Scheme C module.
   Add them to a generated/readable Scheme C model card and README.
9. Mark any bid multiplier as experimental and incompatible with the strict
   bid-at-cost claim unless it equals one.

## Tests

- Defaults reproduce the pre-registry resolved values.
- Invalid types, ranges, enum values and forbidden overrides fail before launch.
- Expected versus stochastic success settings are propagated correctly.
- API schema tests.
- One/two-period execution and retained numerical fixture comparison.
- Retained-source hash test.

## Deliverable

Provide the classification table, precedence rule, advanced-setting schema,
resolved-run example and proof that hidden scientific environment choices were
eliminated or isolated behind the legacy adapter.
