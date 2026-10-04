# Prompt 105 — Matched ten-year fixed-network comparison

Execute only after Prompt 104 is GO. Act as a capacity-expansion validation lead.
The network is fixed for 2025–2034: this prompt must not add transmission
investment or reinterpret the optional expansion interface as an implemented
model.

## Objective

Compare how the same CEM evolves under staged copperplate balancing and optional
zonal redispatch over ten full years, and separate network effects from storage
pricing effects.

## Matched scenarios

At minimum run the following complete 2025–2034 matrix with the same data pack,
signed network pack where applicable, random seed and non-varied modules:

1. staged copperplate + thesis/legacy storage tariff;
2. zonal redispatch + thesis/legacy storage tariff;
3. staged copperplate + dynamic annual-average storage recovery;
4. zonal redispatch + dynamic annual-average storage recovery.

Retain the established Scheme C reproduction output as an external reference;
do not modify or relabel it as a staged or network run.

## Comparison requirements

Report annually and cumulatively:

- capacity, generation, final dispatch, investment, planning and commissioning;
- system resource cost, constraint resource cost, national/redispatch settlement
  and policy transfer ledgers;
- forecast-error and network-constraint counterfactual costs;
- VRE curtailment split, storage utilisation/SOC/cashflow/cost-recovery flags;
- boundary congestion, zone net position, VOLL/EENS/loss-of-load events;
- carbon ledgers and any effect attributable to changed physical dispatch;
- dynamic-storage fallbacks, zero-sale transitions and extreme recovered prices;
- fallback geography and data-quality flags.

Investigate divergence year-by-year. Classify it as intended network physics,
storage-pricing feedback, CEM path dependence, data/mapping effect, numerical
degeneracy or program defect.

## Acceptance

- All four ten-year runs have complete, validated, replayable bundles.
- Scenario inputs differ only on the declared balancing and storage-price axes.
- Every material divergence has a traceable first causal period and classification.
- No conclusion overclaims security, real-line flows, endogenous transmission or
  statistical reliability.

## Deliverables

- four immutable run manifests and comparison bundle;
- annual/cumulative tables and frontend-comparison fixture;
- detailed Markdown/JSON scientific report and release recommendation.
