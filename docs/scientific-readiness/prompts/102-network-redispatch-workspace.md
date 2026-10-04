# Prompt 102 — Network and redispatch workspace

Execute after Prompt 101. Act as a senior scientific frontend engineer. Reuse the
existing FORCE visual language, market replay queries and result APIs. Build a
dedicated **Network & redispatch** workspace; do not overload the run-centre
summary and do not imply that transport corridors are real transmission lines.

## Objective

Let a non-programmer select the optional zonal method, understand readiness,
inspect congestion and trace a half-hour auction from national schedule to final
physical redispatch.

## Study and launch UX

- Show the ahead-market and balancing stages separately.
- Offer thesis-compatible copperplate and zonal network redispatch. Keep the
  full-chronology DC-OPF visibly labelled as a separate experimental/reference
  method.
- Require a signed compatible network pack for zonal launch and show pack ID,
  geography/method scope, lossless/fixed-limit assumptions, mapping fallback and
  ledger disk estimate.
- Do not expose a bundled transmission-expansion selector.

## Results UX

Provide a concise annual brief plus drill-down for:

- zonal demand, generation, net position, redispatch and unserved energy;
- ETYS boundary transfer, forward/reverse capacity, utilisation, congestion
  periods and diagnostic shadow value;
- ahead schedule versus final dispatch by resource;
- economic, weather-change, network-added and total VRE curtailment;
- forecast-error, constraint-resource, settlement, policy and system-cost
  accounts without double counting;
- storage SOC and signed charge/discharge after redispatch;
- observed loss-of-load hours, EENS, events and affected zones;
- full bid/acceptance/payment/reason replay when the full ledger exists.

Map labels must say zones and computational corridors. Link each result to Market
replay and expose exports through the existing result-export workflow.

## Failure UX

Show exact failure status and evidence link. Offer the explicit new-run
`Rerun as copperplate` action with a comparison-parent explanation. Never present
it as continuation of the failed zonal run. Let the user download a diagnostic
bundle with instructions for independent reproduction or reporting the case to
the maintainer.

## Acceptance

- Keyboard, screen-size, loading, empty, partial-ledger and error states pass.
- Summary/full ledgers render the same annual totals.
- Claims and tooltips distinguish physical/resource cost, settlement transfer,
  diagnostic shadow value, observed reliability and unsupported security scope.
- Frontend lint, build and targeted browser journeys pass.

## Deliverables

- backend query endpoints and frontend workspace;
- accessible chart/table/map components and CSV/JSON links;
- browser fixtures for copperplate, congested zonal and failed/rerun cases;
- concise English/Chinese help text.
