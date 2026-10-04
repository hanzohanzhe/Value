# FORCE release-completion execution map - 2026-08-08

This map records how the seven requested release tasks were assigned to Prompts
11-28. It predates the post-Prompt-28 compatibility audit and remains the
authoritative mapping for those seven outcomes; none of them is reassigned to a
second architecture.

The later Prompts 29-34 are narrowly scoped completion work for acceptance
criteria that Prompts 06, 12, 14, 17B, 25 and 28 already established but the
implementation has not yet met. Their evidence and non-duplication boundaries
are recorded in `POST_28_COMPATIBILITY_REMEDIATION.md`.

All work must preserve the retained Scheme C hashes, installed data pack and
historical run bundles. New data, modules, ledgers and outputs belong in versioned
FORCE contracts, adapters and new run bundles.

## Request-to-prompt map

| Requested outcome | Execute | Required evidence |
| --- | --- | --- |
| 1. Code/data rights and a UK open-data aggregation pack | Prompt 14, then Prompt 24 | Per-object rights and attribution inventory; 25-role `force-uk-open-data-pack`; deterministic build; redistributable archive containing only verified files; downloader/adapter for conditional files; synthetic unrestricted pack |
| 2. One headline system cost calculated from the CEM scenario | Prompt 11 | `cem_system_cost_gbp` and GBP/MWh served from commissioned fleet CAPEX/FOM plus PSM physical OPEX and reliability/storage physical costs; no bids/transfers/pipeline/residual double counting; legacy metric retained separately |
| 3. Carbon database connected to total carbon accounting with current and Scheme C scenarios | Prompt 21 | `force_current_authoritative_v1` physical tCO2e ledger; `scheme_c_reproduction_2026_07_18` exact legacy result; immutable factor provenance; mass reconciliation; explicit non-physical status for unresolved legacy storage scalars |
| 4. Weather/demand aggregation, planning success/database, fleet life and residual value | Prompts 18, 19 and 20 | Queryable planning-project index; distinct planning/execution/adequacy rates; weather-demand ensemble summaries; fleet vintage, remaining life and model remaining capital value with source/quality; terminal pipeline reconciliation |
| 5. Cancellation, retention, quota, comparison, export, portable checkpoint and storage-module comparison | Prompts 13, 22 and 23 | Frozen/resumable inputs; lifecycle state machine; safe cancel/archive/restore/delete; quota reservation; portable non-executable checkpoints/bundles; dynamic/legacy/user-module comparison and correctly labelled perfect-foresight counterfactual |
| 6. Foolproof installation, CI and portable paths | Prompts 24 and 25 | Locked dependencies/extras; no developer absolute paths; Windows one-click launch; environment doctor; clean install/upgrade/uninstall; Windows and portable open-core CI; solver/data choices explicit |
| 7. Programmer-flow simulation and short, full two-year and full ten-year tests | Prompt 28 | Clean-checkout contributor workflow; short analytical matrix; 35,040-period two-year CEM transition; two immutable 175,200-period ten-year canonical runs; retained comparison; runtime/disk/hash and scientific gate reports |

## Scientific definitions fixed by these prompts

### CEM system cost

The public headline is a resource-cost view of the annual CEM state. It includes
annualised capital and fixed O&M for commissioned in-service assets, PSM physical
operating cost, storage physical degradation and reliability cost exactly once.
Market settlements, storage cost-recovery bids, subsidies, uncommissioned pipeline
CAPEX and informational residual values remain separate views.

### Carbon scenarios

`force_current_authoritative_v1` is the physical accounting scenario and may
publish total tCO2e only with complete compatible factor coverage.
`scheme_c_reproduction_2026_07_18` reproduces retained formulas. Scheme C storage
scalars 40/50 have no established physical unit, so their exact numeric legacy
result must not be relabelled tCO2e unless the missing source/unit is resolved.

### Success rates

Keep these denominators separate:

- execution completion: completed experiment members / scheduled members;
- adequacy success: completed members meeting a declared adequacy threshold /
  scientifically eligible completed members;
- planning success: realised or expected project/MW outcomes under the selected
  planning mode.

Weather and demand realizations themselves are not described as successful or
failed.

### Residual value

Report asset-specific book value only where an accounting basis exists. Otherwise
report the model remaining capital value as the present value of remaining
annualised CEM capital charges. Market/salvage value remains `not_evaluated` unless
a separately sourced terminal-value policy is selected.

## Execution order

The dependency-safe order is:

1. Prompt 11;
2. Prompts 12-16;
3. Prompts 17A and 17B;
4. Prompts 18-25 in numeric order;
5. Prompts 26 and 27;
6. Prompt 28 initial integrated release audit;
7. Prompts 29-34 in numeric order, followed by a rerun of the Prompt 28 release
   gates as specified by Prompt 34.

Prompt 11 cannot be postponed until after solver work because Prompt 12 and the
perfect-foresight objective both depend on the reconciled cost definition. Prompt
28 must not launch full ten-year runs until preservation, installation, solver,
cost, carbon, checkpoint and short/two-year gates pass. Prompts 29-34 do not
weaken that rule or authorize a long run before the corrected gate is green.

## Canonical long-run pair

Unless a later accepted experiment specification says otherwise, the minimum
release pair is:

1. published FORCE dynamic storage recovery +
   `force_current_authoritative_v1` carbon factors;
2. Scheme C legacy storage tariff +
   `scheme_c_reproduction_2026_07_18` carbon factors.

The optional perfect-foresight PSM and a conformant user module must pass short and
full two-year validation. Include either in the full ten-year matrix before making
an equivalent long-horizon scientific claim for that module.
