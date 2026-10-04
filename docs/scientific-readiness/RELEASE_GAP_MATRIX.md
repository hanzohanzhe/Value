# GridForm release-gap to prompt matrix

This matrix was written after reading both completed prompt sequences in full:

- `docs/visibility-refactor/prompts/01-10`;
- `docs/scientific-readiness/prompts/01-10`.

Prompts 11-28 do not supersede those tasks. They close gaps that remained after
their implementation. Every task must preserve the retained Scheme C hash
boundary and all historical run bundles.

| New prompt | Remaining gap | Existing work to reuse, not repeat |
| --- | --- | --- |
| 11 | The headline system cost is not yet the reconciled annual CEM resource cost of the commissioned fleet and PSM operation | Named annual results, market ledger and storage-cost policies |
| 12 | The public runner still contains copied-kernel/replay and hard-coded built-in resolution paths | Contracts v2, manifests, conformance kit and orchestrator lifecycle |
| 13 | A run revision is identified, but live data can change between enqueue and child-process read | Project fingerprints, provenance and checkpoint hash validation |
| 14 | Imported files are not yet executed through complete canonical adapters and deep/atomic validation | The 25-role data-pack preflight and mapping metadata |
| 15 | Storage technology assumptions remain embedded in code rather than a versioned scientific catalogue | Storage-cost policy contracts and parameter provenance |
| 16 | The dynamic previous-year recovery rule is implemented but its zero-sales/floor sensitivity is not scientifically characterised | Dynamic storage policy and ten-year runs |
| 17A | Users cannot yet select a genuine solver-backed perfect-foresight storage co-optimization PSM through the public module contract | Native runtime cutover, PSM contracts, storage catalogue, cost ledger and market artifacts |
| 17B | Current dispatch checks use a toy solver rather than an independent oracle against the actual public FORCE and perfect-foresight PSM modules | Mechanism fixtures, energy-balance checks, public invocation evidence and retained comparisons |
| 18 | Planning modes lack a complete ensemble workflow and queryable project/outcome database with correct success denominators | Planning causal ledger and seed parameters |
| 19 | Operating assets lack a sourced remaining-life/model-residual ledger and final pipeline has no declared terminal treatment | Planning summaries, annual state chain and cost/lifetime inputs |
| 20 | Weather and demand are single-path and execution, adequacy and planning success rates are not separately aggregated | Data roles, immutable projects and ensemble infrastructure |
| 21 | The carbon database is not connected to a total-emissions ledger with separate authoritative and Scheme C reproduction factor scenarios | Period market ledger, carbon catalogue and annual result contracts |
| 22 | Long runs lack complete cancel/archive/delete/quota/export controls and safe portable checkpoint policy | Atomic checkpoints, resume and artifact index |
| 23 | Results lack a decision-oriented cross-scenario workspace and controlled dynamic/legacy/user storage-module comparison | Bounded APIs, annual results, planning and market audit views |
| 24 | Code/data rights are not release-ready and there is no verified 25-role UK open-data aggregation artifact | Provenance, data adapters and bundle manifests |
| 25 | Installation has environment/path dependencies and is not locked, one-click or reproducibly verified in CI | Python preflight and current launch scripts |
| 26 | Frontend tests do not exercise the real browser workflow, accessibility or failure recovery | Existing rendered-page tests and local API |
| 27 | The public model lacks a complete mathematical reference and bounded scientific claims | Model card, parameter inventory and scientific reports |
| 28 | There is no clean-programmer-flow gate with short, full two-year and full ten-year verification of Prompts 11-27 | Existing Prompt 10 release machinery, extended with the new gates |

## Priority and order

- P0 correctness and truthfulness: 11-17B.
- P1 experimental validity and lifecycle: 18-22.
- P1 product and public release: 23-27.
- Integration gate: 28.

Execute in numeric order unless a prompt explicitly permits independent work.
Do not mark a prompt complete merely because files were created or a process
exited zero. Its acceptance tests and stop condition govern completion.

## Post-Prompt-28 observed implementation gaps

The earlier rows describe the intended Prompt 11-28 work. Inspection of the
current production route found that Prompt 12's no-replay/one-registry acceptance
gate and Prompt 25's portable-path gate are not yet satisfied. The following are
completion prompts, not a new parallel architecture:

| Prompt | Remaining observed defect | Earlier work reused, not repeated | Execution status |
| --- | --- | --- | --- |
| 29 | Two real weather defaults remain in retained `config.py`, and the scanner falsely classifies `year:\\n` as a drive path | Prompts 24, 25 and 28 release machinery | accepted; preserved source isolated from hashed portable runtime copy |
| 30 | Mutable global config, environment, working directory and fixed filenames remain reachable | Prompts 13-14 snapshot and adapter contracts | accepted; confined to hashed `SchemeCRunContext` and one restoring reference session |
| 31 | A private Scheme C registry resolves most slots; only storage cost supports workspace fallback | Prompt 04 conformance and existing workspace registry | accepted; one frozen manifest/source-hashed graph drives every slot and resume |
| 32 | Production runs the whole Scheme C kernel before materialising v2 replay results | Prompt 12 typed lifecycle and Prompt 17B validation specification | accepted; live annual v2 calls, typed results and private reference route proved |
| 33 | Three Scheme C PSM entry routes have overlapping identity and different live/replay semantics | Existing manifests, migrations and reference comparison | accepted; one registered live identity, typed deprecations and private historical reader |
| 34 | Python 3.10 reference constraints are conflated with native-runtime support and release evidence is stale | Prompts 25, 27 and 28 runtime/claims/gates | processed: runtime/package gaps closed; release remains stopped because live FORCE audit inputs are insufficient for Prompt 17B |

The dependency-safe detail is in `POST_28_COMPATIBILITY_REMEDIATION.md`.

## Final Prompt 35–41 validation sequence

| Prompt | Release delta | Status |
| --- | --- | --- |
| 35 | Declare complete solver-neutral inputs before live clearing | completed; live two-period trace, linked hashes and unchanged results |
| 36 | Validate actual FORCE clearing independently over 24 h and 168 h | completed; 74/74 and 521/521 convex stages matched CBC |
| 37 | Classify differences and pass random/mutation gates | completed; three import defects repaired in runtime copy, 20/20 random and all mutations passed |
| 38 | Pass smoke, full one-year and full two-year state-chain gates | completed; smoke, 17,520-period year and 35,040-period two-year chain passed with valid bundles |
| 39 | Run dynamic and legacy-policy canonical ten-year scenarios | executed; both completed, but final CEM audit invalidated their publishable cost/carbon interpretation |
| 40 | Finalize convenient local UK pack and per-object rights ledger | completed for local use; combined public archive remains NO-GO |
| 41 | Compare results and issue final open-source release decisions | completed; platform decision NO-GO |

## Post-long-run remediation

| Prompt | Newly observed release blocker | Status |
| --- | --- | --- |
| 42 | Commissioned assets lack guaranteed next-year live PSM injection and complete economics | accepted; versioned economics fail closed, and 44/44 projects entered the 2026 live FORCE fleet in the full two-year run |
| 43 | Typed CEM has no complete parity proof or declared-divergence specification | accepted as declared divergence; `force-cem-v1` lists the exact retained differences and makes no parity claim |
| 44 | Total-carbon ledger lacks complete authoritative factors and asset-vintage embodied allocation | accepted for the current authoritative scenario; annual direct, import and embodied totals reconcile in JSON and SQLite |

## Post-Prompt-46 architecture closure

These prompts address defects discovered by inspecting Prompt 46 evidence. They
do not repeat or invalidate the accepted Prompt 42–46 run bundles.

| Prompt | Newly observed gap | Earlier work reused, not repeated | Status |
| --- | --- | --- | --- |
| 47 | Commissioned assets can become duplicate investors and headroom is applied per asset rather than per technology-year | Prompt 42 causal coupling and Prompt 43 CEM identity | accepted; stable owner grouping, shared technology budgets and explicit eligibility fixtures pass |
| 48 | Native initial-state preparation does not prove that all advanced planning parameters are effective; commissioning scale lacks a compact audit | Prompt 07/18 planning ledger and index | accepted; immutable preprocessing evidence and commissioning diagnostics pass targeted and native smoke tests |
| 49 | Model-card cost metadata says Scheme C while the ledger implements FORCE CEM resource cost; hydro stock CAPEX needs a hard new-build boundary | Prompt 11 cost ledger and Prompt 42 economics | accepted; definition IDs align and hydro new build fails closed without site and cost-source evidence |
| 50 | The current source tree and dual frontend lock metadata cannot reproduce the full local product from a clean source release | Prompt 25 install/CI and Prompt 45 data separation | partial; deterministic source archive passes, but 449 release members remain untracked in Git pending maintainer staging/commit |
| 51 | Architecture fixes need bounded verification before another long run | Prompt 46 release gates | accepted for bounded verification; 226-test suite, npm lint/build and fresh two-year smoke pass |
| 52 | Post-Prompt-47 annual investment causality and the 2026 REPD cohort remain unverified at full chronology before another ten-year comparison | Prompts 38/39/42/47–51 | accepted; complete 2025, 2025-2026 and paired 2025-2034 runs pass physical, cost, planning, lineage, investment and bundle gates |
| 53 | REPD generic batteries are silently typed as 0.25C; expected-capacity MW is paired with unweighted MWh/CAPEX; superseded reapplications can remain active | Prompt 52 Gate B, without replacing Prompt 48 preprocessing | accepted; explicit proportional storage typing, probability-consistent MW/MWh/CAPEX/FOM and superseded lineage pass cohort and full-run audits |
| 54 | External Windows launcher logs can flush after provenance and invalidate an otherwise sound direct-run bundle | Prompt 22 bundle integrity and Prompt 52 resume evidence | accepted; supervisor logs are outside the scientific artifact boundary and both ten-year reseals preserve every scientific hash |
| 55 | The release audit requires physical carbon reconciliation even for the explicitly non-physical Scheme C reproduction boundary | Prompt 21 carbon scenarios and Prompt 52 legacy run | accepted; physical totals still fail closed while the exact legacy null/reason contract passes |
| 56 | Period-level bids are queryable but users cannot replay how one auction cleared or join final non-duplicated half-hour outcomes into a chronological generation profile | Visibility Prompts 07-08 and scientific-readiness Prompts 08, 23 and 35-37 | implemented at bounded-beta scope; ledger v4, physical dispatch, declared auction read model, APIs, English workspace, runtime bridge fixtures, lint/build and 24 h/168 h/annual synthetic benchmarks pass |
| 57 | The results expose one curtailment number but do not reproduce the thesis distinction between available/delivered VRE, pre-balancing excess generation, balancing curtailment and marginal curtailment | Prompt 56 physical dispatch plus the current period/annual market ledger | implemented at bounded-beta scope; versioned VRE summary/timeline and dedicated page preserve mixed-excess scope and the available = accepted + unused identity; a post-change Python 3.10 full Scheme C run remains a release follow-up |

| 45 | Seven UK data roles are not ready for a combined public archive | accepted per object; 25/25 roles have source/licence labels, attribution, verified files and a clean public-pack scan |

<!-- Prompt 47–51 append below Prompt 46; kept here to avoid changing prior evidence text. -->
| 46 | All scientific runs and release gates must be regenerated after 42–45 | accepted; all declared clearing, annual, causal, ten-year, packaging and per-object data-distribution gates passed for a bounded-claim open-source beta |

## Post-Prompt-58 release alignment

The detailed non-duplication rules and dependency graph are in
`POST_58_ALIGNMENT_PLAN.md`. Prompts 59-64 close only current release deltas;
they do not reopen accepted model equations or repeat full chronology without a
scientific hash change.

| Prompt | Remaining release delta | Existing work reused, not repeated | Status |
| --- | --- | --- | --- |
| 59 | Working tree, demo copy and private GitHub release line are not one canonical tracked source product | Prompt 50 deterministic manifest and existing private upload | local convergence accepted; authenticated connector publication is completed by Prompt 64 |
| 60 | Rights/provenance files can disagree about UK price/policy objects and carbon-factor redistribution | Prompts 24, 40, 45 and 55 object ledgers and built databases | accepted; one generated rights authority governs 25 UK and 10 carbon objects across separate products |
| 61 | The local UK benchmark lacks an ordinary-user atomic data-bundle installation path | Prompt 45 verified bytes and Prompt 58 transactional ZIP defenses | accepted; streaming/atomic ZIP installer, UI and full 639.6 MB UK bundle test pass 25/25 plus live wiring run |
| 62 | Dependency/security evidence needs a current bounded remediation and supply-chain decision | Prompt 25 locks, CI, SBOM and installer | accepted; no high/critical finding, all remaining findings time-bounded, exact install scripts and scoped SBOM enforced |
| 63 | Later-year performance growth and annual-only native recovery remain beta limitations | Prompts 10/22 profiler, lifecycle, quotas and checkpoint identity | bounded accepted; 24/168 h CPU/RSS measured, root cause remains UNKNOWN, annual recovery retained and subannual support truthfully false |
| 64 | No final clean-clone decision is tied to one canonical commit and impact-selected test set | Prompts 46/52 scientific evidence and Prompts 50/59 release tree | Windows clean checkout accepted at runtime commit `d6a5cac`; private-branch publication and remote Linux CI remain external evidence |

Prompts 59-62 are release blockers. Prompt 63 is accepted only if it preserves
scientific identity; an explicit annual-only recovery limitation may remain in a
bounded beta. Prompt 64 is the decision gate and contains no feature development.

## Method-three platform expansion

Prompts 65-71 turn full-domain replacement from documentation into a versioned
extension mechanism. They begin after Prompt 64 and do not block the current
single-node release.

| Prompt | New capability rather than old defect | Existing work reused, not repeated | Status |
| --- | --- | --- | --- |
| 65 | One-registry extension/capability framework, conditional roles, module-owned parameter schemas and namespaced state/artifacts | v2 contracts, 25 base roles, project snapshots and Prompt 58 installer | accepted on separate 0.6 alpha line |
| 66 | Optional run-of-river and conventional-reservoir hydrology | Existing hydro boundary and storage catalogue; pumped hydro remains separate | experimental; analytical/24/168-hour fixtures accepted, real UK and ordinary browser run path not accepted |
| 67 | Solver-neutral network data and PSM contract family | Existing offers, declared clearing inputs, adapters and ledgers | accepted |
| 68 | Independently validated reference DC network PSM | Prompt 36-37 oracle standards and Prompt 67 fixtures | accepted in declared synthetic/reference scope |
| 69 | Optional AC feasibility/OPF modules with truthful convergence/optimality classes | Prompt 67 contracts and Prompt 68 network UI patterns | experimental local feasibility; AC OPF not evaluated |
| 70 | Transmission asset, planning, commissioning and next-year CEM lifecycle | Existing investment/planning/transition/cost/carbon contracts | experimental; causal two-year fixture accepted, national annual pathway not evaluated |
| 71 | Backward-compatible, capability-by-capability expanded-platform release decision | Prompt 64 clean release gate and all selected extension evidence | accepted with capability-specific boundaries |

The order is `64 -> 65 -> 66` and `64 -> 65 -> 67 -> 68/69/70`, followed by
Prompt 71. Prompt 69 is optional and may remain experimental. Ten-year runs are
required only when publishing a new endogenous multi-year scientific pathway or
when an accepted multi-year scientific hash changes.

## Optional staged-market and fixed-network zonal workstream

Prompts 93–106 implement the owner-approved Q1–Q74 design without reopening the
accepted copperplate or Castle 101 paths. Their detailed dependency and
non-duplication rules are frozen in
`ZONAL_REDISPATCH_SUPERSESSION_MATRIX.md`.

| Prompt | New bounded capability or gate | Earlier work reused, not repeated | Status |
| --- | --- | --- | --- |
| 93 | Rollback identity, literal contract IDs and supersession boundary | Prompt 92 tag, retained hashes and Prompt 65–70/77–84 evidence | accepted |
| 94 | National ahead-market result and replaceable balancing contract | v2 contracts, one registry, declared clearing inputs | accepted |
| 95 | Thesis-compatible staged copperplate path | Accepted live bid-at-cost PSM and market ledger | accepted |
| 96 | Fixed lossless zonal transport/cut-set data contract | Prompt 67 conditional network data infrastructure | accepted |
| 97 | Frozen asset-zone allocation and two weather-spatialisation modes | REPD, ERA5/profile adapters and commissioned-asset coupling | accepted |
| 98 | Candidate GB network pack, rights/reconciliation audit and owner sign-off | UK data inventory and deterministic bundle builders | owner-approved, signed and installed locally; complete pack remains outside public source |
| 99 | Independent-half-hour HiGHS zonal redispatch balancing | Prompt 95 staged input and Prompt 96 signed pack | analytical implementation accepted; remains experimental pending Prompt 103 oracle |
| 100 | Zonal settlement, counterfactual and reliability evidence in SQLite v5 | Existing ledger/replay/export infrastructure | accepted; additive v4→v5 migration, six separate accounts, matched counterfactual algebra, curtailment identity, observed reliability events and summary/full invariance pass |
| 101 | Live staged PSM→CEM integration and explicit linked copperplate rerun | v2 orchestrator, project revisions and annual ledgers | accepted; causal owner cashflow, commissioned assets and immutable reruns pass |
| 102 | Dedicated Network & redispatch workspace | Prompt 56 replay and Prompt 83 domain-result patterns | accepted; bounded API, exports, scope labels and browser journeys pass |
| 103 | Independent PuLP/CBC, mutation, random, 24 h and 168 h solver gate | Prompt 36–37 validation standards | planned; blocks annual execution |
| 104 | Matched full-year and causal two-year production gate | Prompt 38/52 run and bundle gates | planned; blocks ten-year execution |
| 105 | Four-case matched 2025–2034 fixed-network comparison | Prompt 39/52 long-run and storage-policy evidence | planned |
| 106 | Bilingual documentation, packaging, clean-clone and bounded release audit | Prompt 64/84/92 release and teaching gates | planned |

This workstream retains the transmission-expansion public contract but bundles no
selectable transmission-CEM implementation. It does not convert the zonal
transport method into a DC, AC, security or N-1 model.

## VALUE 101 teaching-product construction

Prompts 109–117 replace the first-use Castle prototype without creating a
second solver or reopening the accepted PSM/CEM and zonal contracts.

| Prompt | New bounded capability or gate | Existing work reused, not repeated | Status |
| --- | --- | --- | --- |
| 109 | Clean VALUE 101 identity and public/internal capability boundary | Prompts 65–84 registry/frontend contracts and Prompts 85–92 teaching route | implemented; contract, tutorial, staged PSM, internal AC, application and documentation regressions pass |
| 110 | Baseline, Windy and High-demand complete CC0 packs | Prompt 86 generator and the 25-role data contract | implemented; deterministic three-pack build, exact controlled scientific role diffs, conflict-safe installer and real-chain regression pass |
| 111 | Explicit teaching origin, controlled Study cloning, report and scoped reset | Immutable revisions and run lifecycle | implemented; explicit origin survives v1/v2 parsing, clone identity diffs pass, reset is confirmed, recoverable and metadata-scoped |
| 112 | First-use workbench with visible real module chain | Prompts 77–92 frontend and teaching content | implemented; seven-step route, explicit Study/Run split, live seven-module disclosure, unsaved handoff and backend compatibility reasons pass |
| 113 | One-dimensional data and storage-pricing experiments | Existing data-pack and storage-policy replacement contracts | implemented; server proves exact role/dimension diffs before save and guided UI separates selection, preview, Study creation and Run launch |
| 114 | Artifact-backed teaching-window comparison | Market, cost, carbon, storage, VRE and planning ledgers | implemented; three-row server aggregation, no browser annualisation, exact-diff refusal, evidence navigation and scoped reset pass |
| 115 | Optional three-zone fixed-network teaching case | Prompts 93–108 staged zonal implementation | implemented; additive complete pack, matched pair, commissioned-project mapping, unique two-year clock and 96-period live evidence pass |
| 116 | Offline Windows pilot and bilingual manuals | Prompt 91 installer prototype and Prompt 90 teaching material | implemented; current-user offline installer, real progress UI, four-pack isolation, bilingual guide, overlay preservation and installed baseline Run pass |
| 117 | Full software, isolation and 30-minute clean-user gate | Existing release audit and clean-install patterns | in progress; fail-closed auditor red/green fixtures passed |

## VALUE output/context replay architecture

Prompts 118–125 implement the approved bounded-output architecture without
changing accepted market or CEM science. Prompt 118 establishes the contract
boundary only; runtime wiring, ledger migration and long-run gates remain
separate work.

| Prompt | New bounded capability or gate | Existing work reused, not repeated | Status |
| --- | --- | --- | --- |
| 118 | Immutable content-addressed run/year contexts, exact resolver and compact zonal period-domain v2 | Prompt 94 outer balancing contract, Prompt 99 zonal solver and v2 manifest registry | implemented; 7 focused context/manifest contracts pass |
| 119 | Bind contexts once per run/year and supply only current-period slices | Prompt 118 contracts and existing staged lifecycle | implemented; 48-period validation/payload, two-year immutable transition and strict-ref gates pass; Prompt 101 passes 18/18 and the pre-existing Prompt 96 hash mismatch remains unchanged |
| 120 | Authoritative staged/zonal market-ledger v8 and trace-invariant integrity chains | Existing v4-v7 read-only ledger readers | implemented; contiguous append/seal, atomic reliability evidence, fixed table roles, physical redispatch cost, portable profile coverage and byte-identical legacy-read gates pass |
| 121 | Atomic first-failure evidence and annual-boundary recovery | Existing checkpoint/cancellation paths | implemented; all trace profiles, first-wins atomic publication, committed-period cancellation and hash-gated annual-only recomputation pass 7/7 focused checks |
| 122 | Selected-graph output-resource estimate and hard disk gate | Existing quota and readiness contracts | implemented; exact selected cardinalities, isolated bounded calibration, atomic reservation, frozen identities and hard refusal pass 7/7 plus preflight 6/6 |
| 123 | Bounded result queries and on-demand replay/export | Existing replay API and legacy readers | implemented; stable 1,000-row SQL pages, v8 summary/legacy read-only behavior, rights-aware range ZIP/JSONL/CSV and non-blocking export jobs pass focused gates |
| 124 | Trace/readiness controls and bounded long-result frontend | Existing Study/Run UI plus Prompt 122/123 frozen evidence and bounded APIs | implemented; trace truthfulness, readiness rendering, bounded windows/pages and one-job exports pass focused frontend gates |
| 125 | Storage, state-coupling and trace-equivalence decision gate | Prompts 118–124 focused evidence | blocked at first bounded live gate: 48-period output is compact and complete, but the authoritative v8 validator rejects its period science projections/chain and annual science root; later gates not run and ten-year restart not authorised |
