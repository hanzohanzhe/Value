# Prompt 107 — VRE curtailment attribution v2

Execute after the signed zonal-redispatch contracts are stable. This prompt is
the execution contract for the approved VRE Curtailment Attribution v2 design;
its presence does not claim that short, annual or two-year gates have passed.

## Objective

Replace one-directional network-added curtailment accounting with a matched,
auditable attribution that can report both added and avoided effects. Keep
system resource cost, settlement, network physics, CEM, storage, hydrology,
interconnectors, DSR and retained Scheme C behavior unchanged.

## Scientific contract

For realised available VRE \(A_r\), perfect-forecast copperplate VRE dispatch
\(G_{PF}\), forecast-schedule plus realised copperplate dispatch \(G_{CP}\), and
final zonal dispatch \(G_Z\), require

\[
A_r-G_Z=(A_r-G_{PF})+(G_{PF}-G_{CP})+(G_{CP}-G_Z).
\]

Publish the six named quantities needed to read that identity: economic,
forecast-added, forecast-avoided, redispatch-added, redispatch-avoided and final
VRE curtailment. `Redispatch impact` is added minus avoided curtailment. It is
not a pure physical-network label because the transition includes participants'
redispatch response.

Formal VRE is Solar, Onshore wind and Offshore wind. VRE used for demand,
storage charging, export, cross-zone delivery or effective DSR is not curtailed.
Keep hydro spillage, unused imports, storage/network losses and load shedding
separate. Do not assign avoided curtailment a default GBP value or subtract it
again from system cost.

Annual rate is

```text
sum(total_curtailment_mwh) / sum(realised_available_vre_mwh)
```

not the mean of period rates. Keep gross added and avoided values separate
through period, zone, technology and annual aggregation.

## Counterfactual and allocation evidence

`force.vre-counterfactual-snapshot/v1` contains one matched row per executable
VRE object and bid tranche. Require stable run, period, asset, owner, zone,
canonical technology and tranche IDs; MWh units; one lowercase realised-input
SHA-256; and the three dispatch values. Reject missing/mismatched sets, non-finite
values, material negatives and dispatch above availability before attribution.

Within each canonical-technology/tranche group, allocate aggregate copperplate
dispatch in proportion to realised availability. Never redistribute final zonal
dispatch. National final curtailment and net redispatch impact are direct
counterfactual quantities; regional and technology results are attributed under
this published deterministic reference rule.

## Capability and compatibility

The built-in staged adapter is currently the only automatic capture path. It
declares `evidence.vre-counterfactual-snapshot/v1`; its selected balancing
component produces `network.zonal-redispatch-result/v1`, and reconciled evidence
is exposed as `results.vre-curtailment-attribution/v2`.

For a third-party PSM, capability and output declarations establish manifest
compatibility only. The module needs its own execution integration adapter and a
complete v6 ledger/evidence path; full external execution of that path has not
yet been verified. An experimental module without the evidence path may run with
attribution `unavailable`. A v2-producing integration that omits or breaks
evidence must fail the run and write separate failure evidence.

New runs use `gridform.market-ledger/v6` and its separate
`zonal_period_accounting`, `vre_curtailment_period` and
`vre_curtailment_detail` tables. Completed v4/v5 databases remain read-only;
their status is `legacy_partial` and unmeasured avoided-curtailment values are
`null`, never zero. Do not resume a pre-v6 database in place.

## User and release contract

Keep the Run page compact: final curtailment, curtailment rate and Redispatch net
impact. Put the complete decomposition, technology selector, zone/technology
summary and bounded object/tranche evidence in Network & redispatch. Raw dispatch
and reference fields remain available through the bounded curtailment-detail API
and complete v6 SQLite tables; the compact v2 JSON is the run audit artifact.
The waterfall is presentation-only; React must not reconstruct, validate or
repair the identity. Current period/resource exports do not contain the
attribution-specific reference, method or residual fields.

Generate a field dictionary defining every v6 attribution period/detail column,
including units, evidence scope, rate denominator and legacy semantics. Include
the implementation, SQL schema, UI component, design, plan, tests and this prompt
in the source release. Exclude run databases and all `outputs/` content.

## Verification ladder

1. Unit and property tests for added/avoided effects, deterministic allocation,
   tolerance, bounds, set mismatch and solver-order invariance.
2. v6 write/read and read-only v4/v5 compatibility; reconcile SQL, JSON and CSV.
3. Module registry, installation and unsupported-capability conformance.
4. Nullable frontend, presentation-only waterfall, pagination, accessibility,
   lint and production build.
5. Deterministic short, 24-hour, 168-hour, random and constraint-mutation gates.
6. A complete matched 2025 copperplate/zonal gate, followed only after success
   by the causal 2025–2026 state-transition gate.

Stop on the first failed gate. A short smoke is wiring evidence, not annual
scientific validation. Do not start or claim the Prompt 105 ten-year comparison
from this prompt.

## Acceptance

- every period identity reconciles within the declared tolerance;
- matched inputs, module identities and period sets are explicit;
- missing and historical evidence remains nullable with a reason code;
- national direct and regional attributed quantities are labelled separately;
- retained Scheme C hashes and unrelated accounting/physics behavior are
  unchanged; and
- final reports distinguish gates actually run from gates not run.
