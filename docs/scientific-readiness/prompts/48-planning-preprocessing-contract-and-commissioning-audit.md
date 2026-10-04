# Prompt 48 — Planning preprocessing contract and commissioning audit

Continue after Prompt 47. Reuse Prompt 07/18 planning ledgers and Prompt 42 asset
lineage.

## Objective

Make advanced REPD/timeline settings reach the native initial-state adapter and
make annual commissioning scale visible without adding an arbitrary scientific
cap.

## Non-duplication boundary

- Do not create a second planning state machine or a second project database.
- Keep `planning/project-index.sqlite` as the queryable projection of typed
  evidence.
- Do not reinterpret expected-capacity projects as realised success counts.

## Implement

1. Publish a versioned planning-preprocessing contract that owns uncertain-status,
   zombie, minimum-size, maximum-year and timeline parameters. Keep annual
   success-mode and seed parameters owned by the planning module.
2. Pass the resolved immutable parameter set to native initial-state construction.
   Apply supported filtering and timeline choices there and record included and
   excluded counts by reason.
3. Do not pretend that a declared parameter is effective unless an executable
   test proves its effect. Unsupported retained-only details must be identified,
   not silently ignored.
4. Extend the existing planning index summary with annual commissioning counts
   and MW by technology/source/region, opening fleet MW, addition ratios and
   concentration. These are audit metrics, not hard build limits.
5. Defer site-constrained hydro projects with an explicit reason when required
   site/hydrology identifiers are absent; never convert pumped storage into a
   generic battery.

## Acceptance

- Minimum-size, uncertain-status, max-year and mean/median fixtures change the
  prepared state exactly once and leave evidence.
- The planning manifest and preprocessing contract jointly cover every planning
  parameter in the registry with no duplicate owner.
- Commissioning diagnostic totals reconcile to typed commissioning events.
- Missing hydro site data is visible as deferment, not commissioning or a crash.

## Stop condition

Keep the gate failed if a user-visible planning parameter is resolved and
snapshotted but ignored by the actual native preparation path.
