# FORCE expanded-platform private test release

Date: 19 August 2026  
Candidate: Python `0.6.0a1`, frontend `0.6.0-alpha.1`  
Branch: `codex/prompts65-71`  
Prompt 64 base: `c3097d0c6648b2a3d084a9b63541298db3390188`  
Tested runtime commit: `42da6ee9119ccaa47a9c2195bdf1e5ffc6e4afd1`

## Decision

This candidate is a `GO` for a separate private alpha of the versioned extension
platform and for the unchanged Prompt 64 single-node research beta. It is not a
new national network-planning baseline.

The reference DC network clearer is a `GO` for its declared convex,
chronological synthetic cases. Run-of-river and reservoir hydrology, AC
feasibility and endogenous transmission expansion remain `EXPERIMENTAL`. AC
optimal power flow, real-UK hydrology/network data paths, and annual or ten-year
endogenous network pathways are `NOT_EVALUATED`.

These decisions are deliberately capability-specific. An experimental optional
module does not invalidate the separately releasable Prompt 64 single-node
model, and a passing synthetic network fixture is not presented as a validated
Great Britain network study.

## What this independent version contains

| Prompt | Delivered capability | Release state |
| --- | --- | --- |
| 65 | Namespaced, versioned extension and capability registry | `GO` |
| 66 | Separate run-of-river and reservoir-hydro contracts; pumped hydro remains storage | `EXPERIMENTAL` |
| 67 | Solver-neutral buses, branches, network state and PSM contract family | `GO` as platform contract |
| 68 | Chronological SciPy/HiGHS DC network clearing plus an independent angle-eliminated oracle | `GO` for declared reference scope |
| 69 | Polar AC feasibility with a rectangular-coordinate independent oracle | `EXPERIMENTAL`; not AC OPF |
| 70 | Causal transmission-project proposal, planning, commissioning, lineage, cost and carbon lifecycle | `EXPERIMENTAL` |
| 71 | Backward-compatibility, science, package, rights, browser and claim gate | This report |

The frontend resolves the selected modules and their capabilities from the same
registry used by runtime execution. It does not silently redirect a network
study to the retained Scheme C kernel.

## Capability decisions

| Capability or product | Decision | Evidence boundary |
| --- | --- | --- |
| Prompt 64 v2 single-node compatibility | `GO` | Upgrade retained the exact frozen graph hash and module identities |
| General extension framework | `GO` | Namespacing, enable/disable, upgrades, conditional roles, state and artifact isolation passed |
| Run-of-river and reservoir hydrology | `EXPERIMENTAL` | Analytical, 24-hour and 168-hour water/energy checks passed; no real UK hydrology pack evaluated |
| Reference DC network clearing | `GO` | Analytical, random, 24-hour, 168-hour, mutation and independent-oracle checks passed |
| AC feasibility | `EXPERIMENTAL` | Local nonlinear feasibility only; residual and cross-coordinate checks passed |
| AC optimal power flow | `NOT_EVALUATED` | No objective, global-optimality or production AC-OPF claim |
| Endogenous transmission expansion | `EXPERIMENTAL` | Causal two-year fixtures and ledgers passed; no full annual network pathway |
| Real hydrology/network/transmission data packs | `NOT_EVALUATED` | No such real-data pack is distributed or claimed by this test repository |
| Existing single-node annual and ten-year baseline | `GO` | Prompt 64 evidence reused because its frozen selection is scientifically unchanged |
| Expanded annual or ten-year network baseline | `NOT_EVALUATED` | Not required or run because no endogenous national pathway is being published |
| Source package and local website on Windows | `GO` | Deterministic packages, clean clone, lint, build, rendered pages and E2E passed |
| UK research pack redistribution | Separate asset | Absent by design; per-object rights evaluation is outside this source repository |

## Scientific verification

### DC network PSM

Thirteen analytical, random, 24-hour and 168-hour cases passed. The production
formulation and independent oracle use different representations.

| Measure | Maximum observed residual |
| --- | ---: |
| Nodal energy balance | `8.881784197001252e-16 MWh` |
| Angle-to-flow relation | `8.881784197001252e-16 MW` |
| Branch limits, reference angles, SOC bounds, power bounds and terminal SOC | `0` |
| Production versus oracle objective | `1.8189894035458565e-11 GBP` |
| Production equality constraints | `1.7763568394002505e-15` |
| Oracle equality constraints | `8.881784197001252e-16` |

Constraint-mutation fixtures fail for the intended physical reason. The tests
cover thermal generation, VRE, imports, storage, SOC, efficiency, power and
energy bounds, but they do not turn this reference LP into full unit commitment.

### AC feasibility

Across 193 periods (1, 24 and 168 hours), the maximum active-power residual was
`1.4210854715202004e-14 MW`, the maximum reactive-power residual was
`1.7763568394002505e-14 Mvar`, and the equipment-limit violation was zero. Flat
and alternate starts converged to within `6.938893903907228e-18`; voltage
magnitudes matched the rectangular oracle exactly at the reported precision.
This establishes local feasibility for the fixtures, not AC economic dispatch or
global optimality.

### Hydrology

The 24-hour and 168-hour fixtures produced a maximum water-balance residual of
`3.552713678800501e-15`, an oracle equality residual of
`4.218847493575595e-15`, and zero objective difference. Natural-flow hydro and
reservoir hydro are separate from the existing pumped-hydro storage model.

### Transmission expansion

Fixtures passed for congestion-triggered proposals; proposal-to-project-to-asset
lineage; seeded success/failure; delay and retirement; shared budgets; endpoint
validation; complete economic identity; next-year injection into actual DC
clearing; dispatch response; and cost/carbon reconciliation. These are bounded
causal fixtures, not a full annual Great Britain transmission plan.

## Backward compatibility

An actual Prompt 64 `0.5.0b1` wheel was installed and upgraded to `0.6.0a1` in an
environment outside the source tree. The default single-node graph SHA-256 was
identical before and after upgrade:

`4d5be61e6a4e8fa14fce88f32d8ba02ec15b3af2062739a438b19e547cb2a4c4`

The source and selected module identities were also unchanged. Old v2 projects
therefore do not receive an implicit network or hydrology migration. The
retained Scheme C source-hash test passed and its source was not edited.

## Final engineering verification

| Gate | Result |
| --- | --- |
| Python 3.10 complete suite | 321 run; 300 passed; 21 expected skips; 0 failed; 69.883 s |
| Focused Prompts 65/66/68/69/70 plus retained-source checks | 33 passed; 0 failed |
| Frontend lint | passed |
| Production build and rendered-page tests | build passed; 3/3 rendered pages passed |
| Browser E2E | 5/5 passed |
| Clean-clone npm install | 505 packages; lock unchanged; 1 low and 4 moderate advisories; no high/critical finding |
| Source-release scan | 662/662 then-current release members tracked; 0 forbidden members |
| Deterministic Python wheel | 586,070 bytes; SHA-256 `be28946b002b0cba4f7761f16fa53e2d266eb33b36743fd4ff034912658e64f7` |
| Deterministic Python sdist | 513,285 bytes; SHA-256 `eba04096395cf08932ab1a9943eb6052f819972bd93b53b34d4d4a01a5a9e556` |
| Clean installation outside source | passed; native verification and live single-node PSM passed |

The npm advisories are recorded rather than hidden. They are below the existing
high/critical blocking threshold and do not justify claiming that the dependency
tree has no security risk.

## Release-gate defects found and closed

The first Prompt 71 run correctly stopped on stale generated documentation,
missing mathematical inventory and an omitted optional `force-native` runtime.
Prompts 72–76 then closed those release-engineering defects without changing
accepted equations:

- Prompt 72 regenerated module/parameter documentation, corrected the
  mathematical capability boundary and installed the locked optional runtime;
- Prompt 73 updated a stale rendered-frontend assertion to the live registry
  contract;
- Prompt 74 made the source-only rights scan distinguish an absent, separately
  distributed UK pack from a failed installed-pack verification;
- Prompt 75 assigned this materially different test line its own `0.6.0a1`
  identity and proved a real upgrade from Prompt 64;
- Prompt 76 prevented ESLint from treating ignored clean-clone products as
  source, while a deliberately invalid tracked fixture still failed lint.

## Explicit limits

- The DC module is a transparent chronological reference LP, not full thermal
  unit commitment with start-up, minimum-up/down or ramping constraints.
- The AC module is a local feasibility calculation, not AC OPF.
- The hydrology module has no validated real-UK inflow database in this release.
- Transmission expansion has no accepted full-year or ten-year national pathway.
- External Python modules run in process and must be trusted.
- The UK research data pack is not absorbed into the Apache-2.0 source release.
- The existing dynamic-storage and legacy-tariff ten-year evidence belongs to
  the unchanged single-node baseline; it is not evidence for network expansion.

## Conclusion

The independent expanded version is suitable for private installation,
demonstration and bounded scientific development. It preserves the accepted
single-node model while exposing real, replaceable hydrology and network
contracts. It must be labelled an alpha: users may use the reference DC module
within its declared scope, but must not interpret the experimental hydrology, AC
or transmission-expansion modules as a validated Great Britain pathway.

The machine-readable decision is
`publication/prompt71-expanded-platform-release-decision.json`.
