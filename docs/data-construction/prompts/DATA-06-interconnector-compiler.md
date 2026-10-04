# DATA-06 — Interconnector compiler

Execute after DATA-05 passes. Act as an interconnector-data modeller. Keep each
interconnector external to the GB internal fleet and locate its physical GB
landing separately from its economic counterparty.

## Objective

Compile NESO register assets, landing-zone evidence and reproducible allocation
of country-level profiles to physical links.

## Required work

1. Parse the pinned Interconnector Register for project, Connection Site,
   directional capability, status, effective date and host transmission owner.
2. Resolve coordinates from official GSP/substation, connection or operator
   evidence with explicit evidence levels.
3. Assign resolved points to one network zone. When official coordinates remain
   unavailable, implement the declared deterministic nearest-coast DSO method
   and record distance, chosen zone and inference method.
4. Exclude Northern Ireland from internal zones while retaining Irish exchange
   through external assets.
5. Prefer asset-level profiles. If only a country profile exists, allocate it
   among effective assets by period-valid directional capability using
   `capacity_weighted_country_split`.
6. Preserve the original country-profile total per period and enforce each
   asset's sign and import/export envelope.
7. Reject duplicate asset identity, double-counted profiles, unknown landing
   zones and contradictory capability evidence.

## Acceptance gate

- Known examples map deterministically to their declared connection sites and
  network zones.
- Country-profile splits conserve every period and never exceed asset envelopes.
- Positive and negative profiles use the correct directional capability.
- Nearest-coast fixtures are deterministic and always request a named waiver.
- Ireland/Northern Ireland handling cannot create an internal NI zone or double
  count exchange.

## Stop conditions

Stop if a country is treated as a landing point, if a profile is split without
conservation, or if inferred coordinates are presented as official.

## Deliverables

- interconnector and landing compiler;
- asset/profile allocation tables;
- evidence and approximation report;
- DATA-06 gate record and commit.

