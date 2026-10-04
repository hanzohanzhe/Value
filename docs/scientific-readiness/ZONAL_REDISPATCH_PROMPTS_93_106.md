# Zonal redispatch workstream — Prompts 93–106

This is the ordered construction contract for the optional fixed-network FORCE
method agreed on 21 August 2026. The approved scientific design is
`docs/superpowers/specs/2026-08-21-zonal-redispatch-network-design.md`; the
task-level implementation plan is
`docs/superpowers/plans/2026-08-21-zonal-redispatch-network.md`.

The workstream preserves three distinct products:

- the existing GB copperplate and Castle 101 path;
- a staged national ahead market with replaceable balancing;
- an optional lossless zonal transport/cut-set redispatch method.

It does not add transmission expansion to CEM. The Prompt 68 DC-OPF and Prompt
69 AC feasibility work remain separate experimental/reference methods.

## Stage and gate map

| Stage | Prompt | Outcome | Entry gate | Exit gate |
| --- | ---: | --- | --- | --- |
| 0. Preserve | 93 | rollback identity, supersession map, frozen IDs | clean Prompt 92 tree | snapshot and retained hashes pass |
| 1. Split market | 94 | ahead/balancing contracts and registry slot | Prompt 93 accepted | old studies unchanged; contract tests pass |
| 1. Split market | 95 | staged bid-at-cost + copperplate balancing | Prompt 94 accepted | parity and information-leak mutations pass |
| 2. Define network data | 96 | zonal/corridor/cut-set schemas | Prompt 95 accepted | synthetic contract validation passes |
| 2. Spatialise | 97 | fleet, weather and CEM zone allocation | Prompt 96 accepted | national totals and frozen shares reconcile |
| 2. Build UK pack | 98 | signed local GB pack and review evidence | Prompt 97 accepted | **passed: owner signed immutable pack** |
| 3. Solve | 99 | single-period HiGHS zonal redispatch | signed Prompt 98 pack | **passed: analytical and constraint fixtures** |
| 3. Account | 100 | SQLite, settlements and counterfactuals | Prompt 99 accepted | ledgers and identities reconcile |
| 4. Integrate | 101 | real staged PSM→CEM path and rerun lineage | Prompts 99–100 accepted | **passed: causal integration, owner accounting and immutable rerun** |
| 4. Present | 102 | Network & redispatch workspace | Prompt 101 accepted | **passed: API, lint, build and browser journeys** |
| 5. Validate solver | 103 | independent PuLP/CBC oracle | Prompts 99–102 accepted | random, 24/168 h and mutation gates pass |
| 6. Production gate | 104 | full year and causal two-year runs | Prompt 103 GO | annual and two-year report GO |
| 7. Long run | 105 | four matched ten-year cases | Prompt 104 GO | complete classified comparison |
| 8. Release audit | 106 | docs, packaging and bounded claims | Prompt 105 complete | separate release decisions published |

## Hard sequencing rules

1. Prompts are executed in number order. Later work may rely only on accepted
   outputs from earlier prompts.
2. Prompt 98 is a deliberate human gate. A candidate network pack cannot be
   assigned its final ID or used scientifically without explicit sign-off.
3. Prompt 103 blocks annual and long runs. Production HiGHS and independent
   PuLP/CBC formulations must not share matrix-building code.
4. Prompt 104 blocks Prompt 105. A smoke run is not evidence of annual economics.
5. A solver failure is evidence, not permission for an automatic copperplate
   fallback. Copperplate rerun creates a new linked run.
6. Every prompt starts with failing focused tests, preserves retained Scheme C
   hashes, updates its machine-readable evidence and ends with review plus
   verification.

## Long-run experiment matrix

Prompt 105 runs only after the annual gate:

| Scenario | Balancing | Storage pricing | Network expansion |
| --- | --- | --- | --- |
| A | staged copperplate | thesis/legacy tariff | none |
| B | zonal redispatch | thesis/legacy tariff | none |
| C | staged copperplate | dynamic annual-average recovery | none |
| D | zonal redispatch | dynamic annual-average recovery | none |

All other inputs are held constant. The retained Scheme C result is a read-only
external reference, not a fifth mutable run.

## Current status

Prompts 93–102 are complete. The owner-approved real-UK pack is installed locally
as `force-gb-zonal-network-v1-c9e841112c40`; its portable receipt is
`publication/prompt98-signed-installation.json`. The complete data object is not
in the public source tree because it remains rights-governed. Prompt 99's
analytical solver tests pass, but its status remains experimental until Prompt
103 independent validation. Prompt 101 connects the selected staged modules,
owner-level CEM cashflow, commissioned next-year assets and SQLite v5 evidence to
the live path. Prompt 102 adds the dedicated launch/result workspace with
bounded queries, exports and explicit failure reruns. Prompt 103 is the active
next task. No
annual result or long-run evidence is claimed yet.
