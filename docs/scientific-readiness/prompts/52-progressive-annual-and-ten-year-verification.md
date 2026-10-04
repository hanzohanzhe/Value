# Prompt 52 — Progressive annual and ten-year verification

Execute after Prompt 51. Reuse the accepted Prompt 38 annual gate, Prompt 39
storage-policy scenarios, Prompt 42 asset-lineage audit, and Prompt 47–49
contracts. Do not recreate those mechanisms or modify retained Scheme C.

## Objective

Determine whether the post-Prompt-47 FORCE PSM-CEM chain is scientifically and
operationally ready for a new ten-year comparison. Expand the chronology only
after the cheaper predecessor gate passes.

## Frozen inputs

- Native Python 3.10 runtime and registered project-selected modules.
- Local `uk-scheme-c-1000twh` pack, with every bound file hash recorded.
- `existing_decarb_base` and the declared FORCE cost definition.
- Dynamic scenario: current FORCE carbon factors and dynamic annual-average
  storage-cost recovery.
- Legacy scenario: Scheme C reproduction carbon factors and legacy storage tariff.
- Existing Prompt 39 and Prompt 46 outputs are immutable comparison evidence;
  every new run uses a new ID and output directory.

## Ordered gates

### Gate A — source, environment and space preflight

1. Build and hash a current source/configuration rollback archive.
2. Record interpreter, dependency locks, module manifests, project files, data-pack
   manifest and free disk space.
3. Re-run the focused owner/headroom, planning, retained-hash and bundle tests.

Stop if source integrity, Python 3.10 capability, data-pack hashes or the disk
budget fail.

### Gate B — REPD commissioning-cohort audit

1. Trace the 2026 commissioning cohort from the normalised project interface back
   to raw REPD identifiers where available.
2. Report declared and probability-weighted MW by technology, region, development
   status, source completion year and model completion year.
3. Detect duplicate project IDs and probable duplicate name/site/capacity rows.
4. Separate deterministic full-project commissioning from expected-capacity
   fractional commissioning; do not describe expected capacity as a realised
   project success count.
5. Explain every technology remapping, especially battery duration and pumped
   hydro exclusion.

Stop before a decade run if the 2026 cohort cannot be reconciled or if project
probability is applied more than once.

### Gate C — complete 2025 annual run

Run 17,520 half-hour periods with checkpoints and summary market trace. Validate:

- energy balance, blackout accounting, storage SOC/power/energy/efficiency;
- PSM cost components and annual FORCE CEM cost-ledger reconciliation;
- carbon-ledger reconciliation and factor coverage;
- investment-owner grouping and absence of commissioned-child duplication;
- technology-wide expansion-headroom conservation;
- complete CAPEX, FOM, economic life and owner lineage for proposals and assets;
- planning ledger, storage observations and checkpoint/bundle integrity.

Stop if any unexplained mismatch exists or if no interpretable annual investment
decision is produced.

### Gate D — causal complete 2025–2026 run

Run or safely resume the second complete year. Prove that accepted 2025 investment
and planning outcomes enter the actual 2026 FORCE clearing inventory with matching
capacity, owner, CAPEX, FOM, life and technology. Compare uninterrupted and
checkpoint-resumed identities where practical.

Stop if any commissioned asset is missing from clearing, appears more than once,
or changes economic identity during transition.

### Gate E — paired ten-year runs

Continue only after Gates A–D pass. Run the existing Prompt 39 dynamic and legacy
2025–2034 scenarios against the same frozen non-storage inputs. Validate all
175,200 half-hour periods per scenario, annual transitions, ledgers and bundles.

Report, but do not suppress:

- dynamic storage fallback count, zero-sales transitions, denominator floors and
  price extremes;
- annual capacity, investment, retirement and planning-pipeline evolution;
- system cost under the FORCE CEM resource-cost definition;
- operational, imported and embodied carbon under each declared factor scenario;
- runtime, memory, disk and checkpoint recovery evidence.

## Final comparison and decision

Compare the paired post-change runs with Prompt 46 and retained Scheme C only
where cost, carbon and input definitions are compatible. Classify each difference
as software regression, data/preprocessing change, storage-policy effect or
declared FORCE-CEM methodological divergence.

Issue separate GO/NO-GO decisions for:

1. native FORCE clearing and conservation;
2. CEM investment/commissioning causality;
3. dynamic storage policy as a research scenario;
4. legacy reproduction scenario;
5. source release from a fresh Git checkout;
6. synthetic and real UK data distribution.

No short chronology result may be reported as annual economics, and no ten-year
run may start after a failed predecessor gate.
