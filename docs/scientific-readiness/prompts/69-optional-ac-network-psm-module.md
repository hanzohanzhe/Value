# Prompt 69 — Optional AC network PSM module

Execute after Prompts 67 and 68. Act as an AC power-flow/OPF specialist, solver
integration engineer and scientific claims auditor. This is an optional extension
release; inability to install an AC solver must not break the single-node or DC
product. Do not present local nonlinear convergence as proof of a global optimum.

## Objective

Provide a separately selectable AC-capable PSM whose contract explicitly models
voltage magnitude, reactive power, transformer controls and network losses. Make
the exact solving mode visible:

- `ac_feasibility`: AC power-flow/security check of a declared active-power
  schedule; or
- `ac_opf`: active/reactive co-optimization under a declared nonlinear or convex
  relaxation formulation.

Do not silently fall back to DC when the AC module fails or lacks data.

## Additional data and capability contract

Extend Prompt 67 conditionally with the fields an AC formulation actually uses:
base MVA, bus voltage bounds/types, generator reactive limits and voltage set
points, resistance/reactance/charging, transformer taps/phase shift/control,
shunts, branch MVA limits and initial solution where required. Validate per-unit
conversion and record every assumption/default in the run snapshot.

Declare capabilities separately for losses, reactive balance, transformer taps,
contingencies, discrete controls and AC OPF. An absent capability produces an
explicit unsupported reason, not a zero-valued result.

## Scientific implementation

1. Package each AC mode as a normal registered module with exact formulation,
   solver/backend, options, tolerances, licence and source hash.
2. Formulate bus active/reactive balances, voltage variables, branch complex
   power/losses, generator P/Q and declared equipment limits. If a relaxation is
   used, expose relaxation type and exactness diagnostics.
3. Integrate thermal, VRE, imports and storage without changing their economic
   identities. State how active-power storage efficiency and any reactive support
   are represented.
4. Return structured statuses for converged, infeasible, iteration limit,
   numerical failure and unsupported data. Never substitute the last iterate as
   a successful solution without residual gates.
5. Reconcile real-power generation, load, storage and losses; separately report
   reactive balance and voltage/branch violations. Extend cost/carbon only with
   physically defined real-energy effects.
6. Keep AC result artifacts bounded and lazy-loaded. Provide voltage, reactive
   output, losses and violations only when their capabilities are present.

## Validation strategy

- Use published small reference cases whose licences permit redistribution and
  record exact source/version. Include at least a two-bus case and standard small
  meshed cases with transformers, losses and reactive limits.
- Compare power-flow feasibility against a distinct trusted implementation or
  independently calculated analytical case. For AC OPF, compare feasible
  objective and residuals with a distinct formulation/backend where possible.
- Report `LOCAL_SOLUTION_VALIDATED` when only local nonlinear agreement is known;
  reserve `GLOBAL_OPTIMUM_VALIDATED` for a justified bound/certificate.
- Test flat-start/alternate-start sensitivity, binding voltage/reactive/thermal
  limits, infeasibility and poor conditioning.
- Mutation tests remove reactive balance, corrupt per-unit conversion, disable a
  voltage bound, omit losses and force DC fallback; each must fail its gate.
- Prove actual project-selected invocation and unchanged single-node/DC outputs.

## Installation and UI

- Put optional solver dependencies in a separate locked extra/runtime capability.
  The doctor reports licence, platform and binary availability before selection.
- Disable incompatible AC choices with exact missing roles/capabilities. The run
  screen shows formulation and convergence class without exposing verbose solver
  logs; full diagnostics remain downloadable.
- Documentation must distinguish AC feasibility, local AC OPF solution, convex
  relaxation and globally certified optimum.

## Acceptance

- Supported reference cases meet declared active/reactive, voltage, branch and
  loss residual tolerances with reproducible solver metadata.
- Failure and non-convergence never appear as a completed scientific result.
- AC outputs survive snapshot, checkpoint, export/import and comparison without
  being coerced into the DC/single-node schema.
- Optional dependencies do not enter the open-core default install unless the
  documented licence and portability decision permits it.
- No full annual or ten-year run is required for initial experimental release;
  24-hour/168-hour evidence and an explicit maturity label are mandatory.

## Stop conditions

Stop if required AC data are unavailable, solver redistribution/licence is
unclear, residuals do not close, or the implementation can only pass by falling
back to DC. Publish `NOT_EVALUATED` or an experimental local-solution status
rather than an optimality claim.

## Deliverables

- optional AC feasibility/OPF module(s) and conditional data extensions;
- exact equations, capability and solver metadata;
- reference-case, cross-engine, start-sensitivity and mutation evidence;
- AC results workspace additions and bilingual limitations;
- machine-readable Prompt 69 status with bounded scientific claim.
