# Prompt 53 — REPD storage assignment and expected-economics closure

Execute as a defect-remediation gate inside Prompt 52 after the REPD cohort audit.
Preserve retained Scheme C and the Prompt 52 pre-test snapshot.

## Defects demonstrated by Gate B

1. Parameterised native preparation maps every generic REPD Battery project to
   `0.25c_battery`, while retained Scheme C proportionally assigns generic REPD
   storage MW to the four expandable storage technologies.
2. Expected-capacity projects scale power by planning probability but retain
   declared-project energy capacity and CAPEX, breaking fixed duration and
   expected-cost identity at commissioning.
3. Older REPD rows that explicitly name a newer reapplication remain in the
   future pipeline and can later double count a physical development.

## Implement

1. Add an explicit advanced scientific parameter for untyped REPD battery
   assignment. Default to the retained Scheme C proportional four-technology
   split; allow users to select a fixed 1C, 0.5C or 0.25C assumption or exclude
   untyped storage.
2. Preserve one physical REPD project identity while creating typed storage
   components with fixed power/energy ratios, technology-specific economics and
   a shared planning-success draw.
3. Under expected-capacity mode, scale MW, MWh, CAPEX, FOM and annualised cost by
   the same probability exactly once. Under seeded stochastic mode, retain the
   complete project conditional on its single physical-project draw.
4. Exclude a REPD row when its own `Are they re-applying (New REPD Ref)` points to
   another extant Ref ID. Record the exclusion count and retain the current row's
   lineage to its old reference.
5. Distinguish physical projects from typed project components in planning
   diagnostics. Do not call four storage components four independent REPD
   projects.

## Acceptance

- Every commissioned storage component has `energy_capacity_mwh = power_mw ×
  declared_duration_hours`.
- Expected CAPEX and annual cost reconcile to effective, not declared, MW.
- Typed component MW sums to the physical project's expected MW and all
  components share one physical project ID and success draw.
- No superseded REPD Ref ID remains active when its replacement exists.
- The 2026 physical-project and MW totals reconcile before and after typing.
- Retained Scheme C source hashes and unparameterised compatibility fixtures are
  unchanged.

Stop Prompt 52 before annual runs if any identity fails.
