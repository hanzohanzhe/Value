# Prompt 104 — Full-year and two-year zonal production gate

Execute only after Prompt 103 passes and the signed network pack remains
unchanged. Act as a scientific test lead. Use the real 17,520 half-hour chronology
and the actual selected FORCE PSM–CEM chain; do not extrapolate a smoke run.

## Objective

Establish that the staged copperplate and zonal methods work at production scale
for one complete year and through one genuine annual CEM transition.

## Run order

1. Run preflight, disk estimate and a short deterministic smoke for each selected
   method.
2. Run one complete 2025 staged-copperplate case and one complete matched 2025
   zonal case with identical data, seed, modules and storage-pricing method.
3. After both annual cases pass, run matched 2025–2026 cases. The 2026 run must
   use the commissioned fleet, owner economics, planning state, zone allocation,
   storage state policy and cashflow produced by 2025.
4. Run ledger bundle validation, replay checks, interruption/checkpoint checks and
   result-export checks.

## Mandatory audits

- maximum half-hour zonal and national balance residual;
- SOC, resource, boundary and cut-set violations;
- national capacity and demand reconciliation;
- owner/headroom/CAPEX/FOM/lifetime inheritance and next-year injection;
- national, redispatch, policy, resource and constraint-cost reconciliation;
- three counterfactual and VRE-curtailment identities;
- fallback MW, inferred offshore landing and missing-data flags;
- solver failures, VOLL use, EENS and observed loss-of-load hours;
- runtime, peak memory, ledger size and write throughput.

## Stop conditions

Stop before two-year execution if either annual run fails, mismatched inputs are
detected, or an accounting/physics residual exceeds its declared tolerance. Do
not silently repair the signed pack or switch balancing method.

## Acceptance

- Both complete annual cases finish and produce valid bundles.
- Both causal two-year chains finish and 2026 state is traceable to 2025.
- No unexplained difference, double count, missing commissioned asset or hidden
  fallback remains.
- A comparison report clearly distinguishes forecast error, network constraint
  and market settlement effects.

## Deliverables

- immutable run manifests and validated result bundles;
- annual and two-year comparison datasets;
- detailed Markdown and JSON gate report with GO/NO-GO decision.
