# VALUE expanded-frontend release gate

Date: 20 August 2026  
Scope: Prompts 77–84  
Candidate: VALUE Network Extensions 0.6.0-alpha.2  
Decision: **GO for a private, capability-bounded alpha; hydrology browser execution remains NO-GO**

## What this decision means

The expanded frontend is no longer a catalogue-only shell. A Study created in
the browser now carries the module map, selected extensions, extension
parameters, conditional data roles and versioned maturity acknowledgements into
the same server-owned registry used by save, preflight, snapshots and live
execution. DC, AC-feasibility and transmission-expansion result pages query
immutable model artifacts; React does not recalculate scientific outputs.

This is not a new national scientific baseline. The accepted UK data path is
still single-node. The reference DC workflow is ready only in its declared
synthetic/linear scope. AC feasibility and transmission expansion remain
experimental. No real-UK network, hydrology or national expansion data pack has
been accepted. No annual or ten-year expanded-network run was requested or used
to strengthen those claims.

## Rollback identity

Prompt 77 began from annotated tag
`expanded-ui-pre-prompt77-20260820`, peeled commit
`c46c6f6c795cea0462a8ee05cddf0122daf951c5`. Prompts 78–83 were frozen at tag
`expanded-ui-post-prompt83-20260820`, peeled commit
`f2baf3caf79f68822b6e78c16c23c5d02b82eb59`. The original Scheme C retained
source was not edited.

## Delivered changes

| Prompt | Delivered behavior |
| --- | --- |
| 77 | Frozen frontend/API truth contract, interaction states, starting gaps and rollback identity |
| 78 | Extension-aware workspace, draft resolution, project save, revision, preflight and snapshot graph identity |
| 79 | Five-step Studies composer: identity, system domain, optional domains, model chain and exact review |
| 80 | Study-conditioned Data groups, parser truth, templates, bounded previews and missing-role navigation |
| 81 | Separate transactional `force.extension-bundle/v1` install/upgrade/enable/disable lifecycle with in-use protection |
| 82 | Canonical topology, hydrology and expansion input previews with corrective actions |
| 83 | Read-only capability, DC period/branch, AC-feasibility and expansion result APIs plus Network & water UI |
| 84 | Clean-clone, browser, accessibility, packaging, rights/dependency and documentation gate |

## Prompt 84 defect found and fixed

The first wheel-only test exposed an optional-dependency leak. A default
`force-native` environment deliberately does not install SciPy, but registry
construction imported the experimental AC and DC solver modules eagerly. This
made the accepted single-node runtime fail even when neither optional module was
selected.

SciPy imports now occur at the DC/AC execution boundary. Registry construction,
catalogue display and the default single-node graph work without SciPy. Selecting
a SciPy-backed PSM still causes runtime preflight to require the solver extra;
direct callers fail with a domain-specific missing-capability error. A subprocess
regression blocks `scipy` explicitly and proves that the base registry still
loads.

The first complete Python run also exposed two base-Study preflight regressions:
optional-domain adapter resolution was running for an unselected single-node
Study. The fix confines network/expansion adapter resolution to selected domains.
Both defects were introduced on the expanded line and do not alter a model
equation.

## Verification

| Gate | Result |
| --- | --- |
| Clean-clone Python 3.10 suite before final documentation | 341 run; 341 passed or expected skip after compatibility fix; 21 expected UK-pack skips; 0 failed |
| Final source Python suite | 342 run; 321 passed; 21 expected UK-pack skips; 0 failed |
| Prompt 46/65–70/78/80–83 focused suite | 63/63 passed |
| Optional-solver import regression | 5/5 runtime-capability tests passed |
| Frontend lint | passed |
| Frontend production build and rendered assertions | passed; 3/3 rendered tests |
| Browser E2E | 7/7 passed, including real external module/two-year smoke, recovery, responsive layout and accessibility; final fresh clone remained Git-clean |
| Accessibility | no critical or serious axe finding in expanded result workflow |
| Reference DC science | Prompt 68 analytical, 24 h, 168 h, random, island and mutation tests passed |
| Hydrology science fixtures | Prompt 66 analytical, 24 h, 168 h, water balance and pumped-hydro non-duplication tests passed |
| AC feasibility fixtures | Prompt 69 1 h, 24 h and 168 h polar/rectangular checks passed; no AC OPF claim |
| Transmission expansion | Prompt 70 causal two-year injection and cost/carbon lineage tests passed |
| Wheel/sdist | built twice byte-identically |
| Wheel-only default-native install | passed outside the source tree, with no SciPy or reference-only packages |
| Dependency audit | GO under recorded time-bounded decisions; no high/critical advisory |
| Retained Scheme C hashes | passed |
| Source-release scan | passed; 707/707 release members tracked; zero forbidden members |
| Rights and runtime-path scan | GO; zero blocking issues |

The deterministic Python artifacts are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `value_network_extensions-0.6.0a2-py3-none-any.whl` | 614,986 | `d077bc9adbd6de756a93aa5820555ceadaa651ca10a4cf5f4147f86dcce8206c` |
| `value_network_extensions-0.6.0a2.tar.gz` | 539,558 | `9f329a1a17edbfc3c9f18dcfa15bb02bee96e4602add23abf29256be2f841d0f` |

The deterministic source/website archive contains 707 tracked files, is
3,896,142 bytes and has SHA-256
`fec4c8c5410197680704f9321940cd07505b201c54bb5caf95c5d2799b780c8c`.
The UK public-data asset and historical run outputs are deliberately separate
products and are not embedded in this archive.

## Required journey decisions

### Unchanged single node — GO

An old v2 Study with no extension fields resolves to the same no-extension graph.
The real browser E2E installs/uses the synthetic pack, saves through the new
composer and runs the selected external module through a two-year smoke path.
The sidebar remains usable at narrow height after adding the new workspace page.

### Reference DC — GO in declared reference scope

The browser exposes the network contract, the four required network roles,
templates/previews, graph review and artifact-backed nodal/branch pages. The
production solver has independent 24/168-hour and random convex evidence and its
result query rechecks branch ratings, flow sign and nodal balance before display.
This does not establish a real-GB network baseline, unit commitment, losses,
reactive power or N-1 security.

### Hydrology — NO-GO for ordinary browser execution

The UI can select the experimental extension, show its five roles and validate
run-of-river/reservoir inputs. The scientific module passes independent fixtures
and refuses to treat pumped hydro as natural-flow hydro. However, the ordinary
annual application does not yet inject those resources into the selected PSM and
emit the declared `force.hydrology-period-results/v1` index. The result API
therefore truthfully returns `not_evaluated`; the browser does not reconstruct
water quantities. This is an affected-workflow NO-GO, not a failure of the
single-node or DC product.

### Experimental AC feasibility — EXPERIMENTAL

The composer requires the network and AC data contracts plus a version-pinned
acknowledgement. Preflight inspects P/Q limits, reactive demand and the declared
active schedule. The result page says **Not AC OPF** and reports convergence,
residuals, voltage and losses from the typed artifact. Missing SciPy fails before
launch. No economic dispatch or global optimum is claimed.

### Transmission expansion — EXPERIMENTAL

The browser composes the DC PSM, expansion contract and optional
`network_expansion` module, previews candidate identity/budget data and traces
candidate → proposal → planning → commissioned/failed/retired artifacts. Prompt
70 proves causal next-year injection in a bounded two-year fixture. No annual or
ten-year national pathway and no counterfactual welfare benefit is claimed.

### Third-party extension — GO for trusted local packages

The Prompt 65 toy extension installs transactionally, contributes a role and
parameter, survives project/snapshot identity, executes through the normal
application and cannot be disabled while referenced by a saved Study. External
Python runs in process and must be trusted; this is not sandboxing.

### Negative journeys — GO within implemented boundaries

Stable errors and corrective actions cover missing solver, required role,
licence/trust acknowledgement, capability, endpoint/mapping, maturity
acknowledgement, extension version, archive bounds and disk headroom. Unknown
fields and identities fail closed rather than being ignored.

## Capability decisions

| Capability | Decision | Boundary |
| --- | --- | --- |
| Single-node UI compatibility | `GO` | Existing v2 graph is not migrated |
| Extension installation | `GO` | Trusted local in-process Python only |
| Study composition | `GO` | One registry owns preview/save/preflight/run identity |
| Conditional Data | `GO` | Shipped parsers/templates; manifest-only formats remain unavailable |
| DC workflow | `GO` | Declared synthetic/reference linear scope only |
| Hydrology workflow | `NO_GO` | Ordinary annual PSM injection and typed result index absent |
| AC feasibility workflow | `EXPERIMENTAL` | Local feasibility of declared schedule; not AC OPF |
| Transmission expansion workflow | `EXPERIMENTAL` | Causal bounded fixture; no national annual/ten-year baseline |
| Results exploration | `GO_WITH_BOUNDARIES` | DC is GO; AC/expansion experimental; missing hydrology is not fabricated |
| Real network/hydrology data packs | `NOT_EVALUATED` | No accepted distributable real-UK pack |

## Developer intervention still required

1. Connect the canonical hydrology pack adapter to the ordinary annual PSM input
   factory, preserving information structure and electrical-asset/site mapping.
2. Emit and index `force.hydrology-period-results/v1` from that live path, then
   add bounded water-period queries and a real E2E run.
3. Assemble, rights-audit and scientifically accept a real-UK network/hydrology
   pack before making a national claim.
4. Run annual and multi-year network/expansion baselines only after such a claim
   is intended; the present bounded fixtures must not be relabelled as one.
5. Re-review accepted dependency advisories by their recorded expiry dates or
   remove/upgrade the affected development-only paths.

## Final release statement

VALUE 0.6.0-alpha.2 is suitable for local private demonstration and controlled
research development. Non-programmers can configure the accepted single-node
model and the bounded DC workflow without editing JSON, and can inspect
artifact-backed experimental AC/expansion evidence. It is not yet a public
real-UK network/hydrology modelling baseline. The hydrology browser workflow
must remain disabled or explicitly `not_evaluated` until the two missing live
connections above are implemented and tested.

Machine-readable companions:

- `publication/prompt84-expanded-frontend-release-decision.json`
- `publication/prompt84-claim-evidence-matrix.json`
- `publication/prompt84-clean-clone-log.json`
- `publication/prompt84-dependency-audit.json`
- `docs/frontend/EXPANDED_FRONTEND_FIELD_MAP.md`
