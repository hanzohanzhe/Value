# GridForm scientific-readiness implementation package

This package follows the completed visibility-refactor prompts. It is the ordered
engineering plan for turning the working modular PSM/CEM chain into an externally
extensible product; release eligibility is decided separately by Prompt 28.

## Preservation boundary

Every prompt must preserve the hashes in
`docs/visibility-refactor/retained-source-hashes.json`. In particular, do not
edit the retained `compat/case3.py`, `compat/simulation_model.py`,
`exact_run.py`, the authoritative fixture, historical run directories, or the
installed Scheme C data-pack contents. Changes belong in the copied modular
implementation, public contracts, adapters, tests and new run bundles.

## Ordered prompts

1. `prompts/01-scientific-acceptance-baselines.md`
2. `prompts/02-storage-cost-policy.md`
3. `prompts/03-run-classification-and-publication.md`
4. `prompts/04-external-module-conformance.md`
5. `prompts/05-project-revisions.md`
6. `prompts/06-data-pack-preflight.md`
7. `prompts/07-planning-causal-ledger.md`
8. `prompts/08-fast-market-artifacts.md`
9. `prompts/09-run-preflight-and-estimates.md`
10. `prompts/10-performance-recovery-and-release.md`

The final release audit found additional gaps that the first ten prompts did not
close. Their non-overlapping scope is recorded in
`RELEASE_GAP_MATRIX.md`. Continue with:

11. `prompts/11-reconciled-cost-accounting.md`
12. `prompts/12-real-module-runtime-cutover.md`
13. `prompts/13-immutable-run-input-snapshots.md`
14. `prompts/14-executable-data-adapters.md`
15. `prompts/15-storage-technology-catalogue.md`
16. `prompts/16-dynamic-storage-robustness.md`
17. `prompts/17-independent-psm-validation.md` (umbrella)
    - `prompts/17a-optional-perfect-foresight-psm.md`
    - `prompts/17b-independent-multi-engine-psm-validation.md`
18. `prompts/18-planning-stochastic-ensembles.md`
19. `prompts/19-terminal-horizon-treatment.md`
20. `prompts/20-weather-demand-ensembles.md`
21. `prompts/21-carbon-accounting-ledger.md`
22. `prompts/22-run-lifecycle-retention-and-safe-recovery.md`
23. `prompts/23-results-comparison-workspace.md`
24. `prompts/24-open-source-and-data-publication.md`
25. `prompts/25-reproducible-installation-and-ci.md`
26. `prompts/26-browser-e2e-and-accessibility.md`
27. `prompts/27-mathematical-reference-and-claims.md`
28. `prompts/28-public-beta-release-gate.md`

The post-gate audit found that several acceptance conditions from visibility
Prompt 06 and scientific Prompt 12 remain incomplete in the actual Scheme C
production route. Their non-duplicating delta is documented in
`POST_28_COMPATIBILITY_REMEDIATION.md`. Continue in order with:

29. `prompts/29-compatibility-path-and-scan-truth.md`
30. `prompts/30-run-scoped-scheme-c-context.md`
31. `prompts/31-one-registry-all-module-slots.md`
32. `prompts/32-live-scheme-c-v2-psm-cutover.md`
33. `prompts/33-consolidate-psm-entry-points.md`
34. `prompts/34-runtime-tiers-and-post-cutover-release-gate.md`

The final validation and local-data sequence requested after Prompt 34 is:

35. `prompts/35-pre-clearing-declared-input-artifact.md`
36. `prompts/36-independent-force-clearing-validation.md`
37. `prompts/37-force-discrepancy-random-and-mutation-gate.md`
38. `prompts/38-gated-smoke-one-and-two-year-validation.md`
39. `prompts/39-canonical-ten-year-storage-policy-runs.md`
40. `prompts/40-local-uk-data-pack-and-rights-ledger.md`
41. `prompts/41-final-comparison-and-open-source-release-audit.md`

Prompt 41 completed the requested sequence but returned a release NO-GO after
the long runs exposed commissioned-asset cost and live-clearing defects. The
smallest non-overlapping remediation sequence is:

42. `prompts/42-commissioned-asset-economics-and-live-psm-coupling.md`
43. `prompts/43-cem-parity-or-declared-divergence.md`
44. `prompts/44-total-carbon-accounting-closure.md`
45. `prompts/45-uk-public-data-distribution-closure.md`
46. `prompts/46-clean-release-regeneration-and-audit.md`

The post-Prompt-46 architecture, full-run and usability closure continued with:

47. `prompts/47-investment-owner-and-expansion-budget-closure.md`
48. `prompts/48-planning-preprocessing-contract-and-commissioning-audit.md`
49. `prompts/49-force-cost-identity-and-hydro-capex-boundary.md`
50. `prompts/50-reproducible-source-release-tree.md`
51. `prompts/51-post-closure-targeted-verification.md`
52. `prompts/52-progressive-annual-and-ten-year-verification.md`
53. `prompts/53-repd-storage-and-expected-economics-closure.md`
54. `prompts/54-external-launcher-log-bundle-boundary.md`
55. `prompts/55-scenario-aware-carbon-release-gate.md`
56. `prompts/56-market-auction-replay-and-dispatch-explorer.md`
57. `prompts/57-vre-excess-and-curtailment-explorer.md`
58. `prompts/58-easy-local-module-installation.md`

The audit after Prompt 58 is consolidated in
`POST_58_ALIGNMENT_PLAN.md`. It separates current single-node public-beta closure
from optional method-three platform expansion. Execute the release line first:

59. `prompts/59-canonical-git-release-line-convergence.md`
60. `prompts/60-authoritative-rights-and-carbon-distribution-ledger.md`
61. `prompts/61-transactional-data-pack-bundle-installation.md`
62. `prompts/62-dependency-security-and-supply-chain-closure.md`
63. `prompts/63-measured-performance-and-subannual-recovery-closure.md`
64. `prompts/64-canonical-clean-clone-public-beta-gate.md`

Only after Prompt 64, build the separately versioned method-three extension line:

65. `prompts/65-versioned-extension-and-capability-framework.md`
66. `prompts/66-run-of-river-and-reservoir-hydrology-extension.md`
67. `prompts/67-network-data-and-psm-contract-family.md`
68. `prompts/68-reference-dc-network-psm-module.md`
69. `prompts/69-optional-ac-network-psm-module.md`
70. `prompts/70-transmission-expansion-cem-lifecycle.md`
71. `prompts/71-expanded-platform-release-gate.md`

Prompts 65–71 were implemented on the separate `0.6.0-alpha.1` expanded test
line. Prompt 71 accepted the extension framework and reference DC scope while
retaining experimental/not-evaluated boundaries for hydrology, AC feasibility,
transmission expansion and real-data pathways. Prompts 72–76 closed bounded
release-engineering defects discovered by that gate.

The completed non-overlapping workstream connects those existing contracts to
the ordinary browser workflow. Its scope and dependency map are in
`FRONTEND_EXPANSION_PROMPTS_77_84.md`:

77. `prompts/77-expanded-frontend-truth-and-contract-audit.md`
78. `prompts/78-extension-aware-workspace-and-study-api.md`
79. `prompts/79-capability-led-study-composer.md`
80. `prompts/80-conditional-data-workspace.md`
81. `prompts/81-extension-bundle-lifecycle-ui.md`
82. `prompts/82-domain-readiness-and-input-previews.md`
83. `prompts/83-network-hydrology-and-expansion-results-workspace.md`
84. `prompts/84-expanded-frontend-release-gate.md`

The approved optional fixed-network workstream is specified in
`ZONAL_REDISPATCH_PROMPTS_93_106.md`. It introduces a staged national ahead
market and replaceable balancing layer before adding lossless zonal redispatch;
it does not add transmission expansion to CEM:

93. `prompts/93-zonal-redispatch-contract-freeze.md`
94. `prompts/94-staged-market-contract-family.md`
95. `prompts/95-thesis-compatible-staged-copperplate.md`
96. `prompts/96-zonal-transport-data-contract.md`
97. `prompts/97-spatial-fleet-weather-and-cem-allocation.md`
98. `prompts/98-gb-zonal-benchmark-build-and-signoff.md`
99. `prompts/99-single-period-zonal-redispatch-solver.md`
100. `prompts/100-zonal-ledger-accounting-and-results.md`
101. `prompts/101-live-staged-psm-cem-integration.md`
102. `prompts/102-network-redispatch-workspace.md`
103. `prompts/103-independent-zonal-validation.md`
104. `prompts/104-annual-and-two-year-zonal-gate.md`
105. `prompts/105-matched-ten-year-zonal-comparison.md`
106. `prompts/106-zonal-release-documentation-and-audit.md`
107. `prompts/107-vre-curtailment-attribution-v2.md` — revised attribution
     execution contract; it does not itself claim a passed validation gate.

Prompts 77–83 are implemented; Prompt 84 records capability-specific release
decisions rather than converting experimental science into a baseline. Within
Prompt 17, execute 17A before 17B. A later prompt may
rely only on accepted code and tests from earlier prompts. Short runs establish
mechanism and integration behaviour; only a 17,520-period run may publish annual
scientific economics.

The seven user-requested release outcomes for cost, carbon, data aggregation,
fleet/planning evidence, lifecycle controls, installation and tiered testing are
mapped to these existing prompts in
`REQUESTED_RELEASE_EXECUTION_MAP_2026-08-08.md`. That map adds no parallel
architecture and is the acceptance index for this workstream.

## Completion status

Prompts 01-10 are implemented and tested. Prompts 11-27 were executed as the
0.5.0-beta.1 engineering candidate, with partial/deferred rows recorded in the
individual reports. Prompt 28 originally stopped at its rights gate; the owner has
since licensed code, documentation and synthetic data. Prompts 29-33 now close
portable paths, run-scoped state, one-registry resolution, live v2 execution and
ambiguous PSM identities. Prompts 34–41 have now been executed. The actual FORCE
convex clearing passed independent CBC validation, and the one-, two- and two
ten-year runs completed. Prompt 41 nevertheless returns NO-GO because the long
runs exposed defects outside that validated clearing stage. Prompts 42–46 are the
remediation sequence, not unexecuted parts of Prompts 35–41.

| Prompt | Remaining delta | Status |
| --- | --- | --- |
| 29 | Correct path false positive and isolate real retained `E:` defaults from portable runtime | accepted |
| 30 | Replace ambient mutable state with one run-scoped compatibility boundary | accepted |
| 31 | Resolve all slots from the existing workspace registry | accepted |
| 32 | Execute live Scheme C PSM through v2; make replay reference-only | accepted; architecture cutover GO, annual scientific parity remains separately gated |
| 33 | Consolidate ambiguous PSM entry points and identities | accepted |
| 34 | Separate native/reference runtimes and rerun Prompt 17B/28 gates | accepted as runtime prerequisite; final FORCE clearing validation completed in Prompts 35–37 |
| 35–37 | Declare and independently validate live FORCE clearing | accepted within the declared convex information structure |
| 38 | Smoke, full one-year and causal two-year execution | accepted as execution evidence; later cost interpretation invalidated by Prompt 41 |
| 39 | Dynamic and legacy ten-year execution | completed; retained as immutable negative evidence because CEM costs/state coupling failed final audit |
| 40 | Local UK pack and rights ledger | local GO; combined public archive NO-GO |
| 41 | Final comparison and release audit | completed; platform NO-GO |
| 42 | Versioned commissioned-asset economics and next-year live FORCE coupling | accepted; full two-year run coupled 44/44 commissioned projects and reconciled the GBP 676.179m capital increase |
| 43 | CEM parity or declared-divergence identity | accepted as `force-cem-v1`, Scheme C-derived with seven explicit divergences and no numerical-reproduction claim |
| 44 | Total-carbon accounting closure | accepted for the current authoritative scenario; direct, import and embodied components reconcile in JSON and SQLite |
| 45 | Per-object UK public-data distribution closure | accepted; 25/25 roles pass source, licence-label, hash and semantic gates with attribution |
| 46 | Clean regeneration and final release audit | accepted; 24/168-hour independent validation, one-year, causal two-year, dynamic ten-year and legacy-tariff ten-year gates passed; release decision is GO for an open-source beta with bounded claims |
| 47–55 | Architecture closure, full chronology, REPD identity, launcher boundary and carbon-scenario truth | accepted; see the release-gap matrix and Prompt 52 evidence |
| 56 | Auction replay and chronological dispatch explorer | implemented at bounded-beta scope |
| 57 | VRE excess and curtailment explorer | implemented at bounded-beta scope; post-change real-data annual evidence remains governed by change impact |
| 58 | Transactional local module-bundle installation | implemented with conformance/security boundaries; in-process code is not a sandbox |
| 59–63 | Canonical source, rights, data installation, dependency security and measured recovery closure | executed; Prompt 63 retains an explicit annual-only recovery limitation |
| 64 | Canonical clean-clone public-beta gate | Windows clean checkout passed at runtime commit `d6a5cac`; private-repository publication and remote Linux CI close the external publication identity |
| 65–71 | Method-three hydrology/network platform expansion | implemented and gated on the separate 0.6 alpha line; decisions are capability-specific |
| 72–76 | Prompt 71 documentation, runtime, frontend-contract, rights-scan, version and lint remediations | accepted; no scientific-equation change |
| 77–84 | Extension-aware frontend composition, conditional data, lifecycle, previews, results and release gate | implemented and gated; hydrology browser execution remains workflow-specific `NO_GO`, while AC and transmission expansion remain `EXPERIMENTAL` |
| 85–92 | Castle 101 teaching model, learning workflow, manual and 30-minute gate | implemented on the teaching workstream |
| 93–107 | Staged market and optional fixed-network zonal redispatch | Prompts 93–102 accepted; Prompt 107 supersedes the one-directional VRE-curtailment accounting contract without claiming that its short, annual or two-year gates have run; no annual zonal scientific result claimed yet |

| Prompt | Delivered capability |
| --- | --- |
| 01 | Separate execution, contract, mechanism and retained-comparison gates |
| 02 | Dynamic, legacy and safe user-formula storage-cost policies shared by PSM and storage expansion |
| 03 | Diagnostic versus annual-scientific run classification |
| 04 | Executable external-module conformance before launch |
| 05 | Immutable research-project revisions and canonical fingerprints |
| 06 | Semantic data-pack validation for all 25 required interfaces |
| 07 | Reconciled causal planning ledger with project stages and outcomes |
| 08 | Bounded SQLite market evidence and optional Parquet export |
| 09 | Python, data, module, parameter, disk and output preflight |
| 10 | Performance evidence, atomic recovery, source-bound resume, bundle validation and three-scenario comparison |

## Final experiment

Only after Prompts 42–45 pass should Prompt 46 create new immutable 2025–2034
projects through the same public application service:

- dynamic annual-average storage-cost recovery;
- retained Scheme C storage tariffs selected as a storage-cost policy.

The existing Prompt 39 projects must remain unchanged as evidence of the defects
that stopped release.

Prompt 46 is complete. The regenerated runs prove cumulative commissioned-asset
lineage, asset-level economics, annual cost closure and annual carbon closure.
The result does not claim exact retained Scheme C numerical reproduction. The
dynamic storage-cost method remains a selectable published research policy, and
later-year runtime and memory use remain beta-quality performance limitations.

Compare both with the read-only 2026-07-18 `existing_decarb_base` Scheme C
result. Report execution, invariants, yearly economics, capacities and deltas.
Do not describe the legacy-tariff modular run as an exact reproduction unless
the comparison actually satisfies the declared tolerance.

The older pre-Prompt-11 experiment is retained in `TEN_YEAR_RELEASE.md` as archived
engineering evidence only. The current versioned decision is
`publication/release-report-0.5.0-beta.1-post-prompt34.md`; it contains no new two-year-full or
ten-year bundle IDs. Owner-controlled licence choices are now resolved, but the
post-gate independent-validation/runtime evidence and third-party UK-data rights
remain separate release decisions.
