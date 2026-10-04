# Prompt 27 — Formal mathematical reference and bounded scientific claims

Continue from accepted Prompt 26. Read the model card, parameter inventory,
contracts, copied modular equations and validation reports. Act as a power-system
modeller and technical author.

## Objective

Publish a precise mathematical and algorithmic reference for what GridForm PSM/CEM
does, does not do and which claims its tests support. Documentation must follow the
executed public modules, not an intended architecture.

## Implement

1. Document sets, indices, time step, units, system boundary, state variables,
   inputs and outputs for the built-in Scheme C-derived module set.
2. Specify PSM clearing and bid construction, including VRE voluntary curtailment,
   thermal/import bids, storage charging/discharging/SOC/efficiency/dwell and
   unmet-demand treatment. State deterministic ordering/tie rules.
3. State the exact limited equivalence: thermal bid-at-marginal-cost dispatch is
   equivalent to the declared single-period convex economic-dispatch case only
   when omitted unit-commitment/ramping/network constraints are not required.
4. Explain that storage's dynamic annual cost-recovery bid is an agent pricing rule
   with intertemporal state, not automatically proof of globally minimum system
   cost. Separate resource-cost, settlement and policy-transfer equations using
   Prompt 11 terminology.
5. Document CEM agent investment logic, VRE/storage caps, expected/stochastic
   planning success, pipeline timing, annual state transition, terminal policy and
   path dependence. State that this is not a perfect-foresight global capacity
   expansion optimum unless a future module explicitly implements one.
6. State the network boundary accurately: the current built-in scenario is a
   copperplate/single-node model without internal transmission constraints;
   interconnectors are exogenous import resources, not an external network model.
7. Document cost, carbon and energy-balance ledgers; dynamic versus legacy storage
   policies; first-year full-utilisation assumption; weather/demand/seed ensemble
   meanings; data transformations and terminal treatment.
8. Generate or cross-check parameter/module tables from the runtime schemas so
   versions, defaults, units and fixed/editable classifications cannot drift.
9. Add a limitations and validation-evidence matrix mapping each scientific claim
   to analytical, independent-oracle, modular regression or retained-reference
   evidence. Mark unsupported claims `not_evaluated`.
10. Update the English README to guide a non-programmer from installation through
    synthetic example, UK data connection, project revision, run modes, results
    interpretation, extension contracts and citation.

## Tests and acceptance

- Equation symbols and units pass a documentation consistency check against public
  contracts/parameter schemas.
- An implementation source scan maps every documented built-in stage to its real
  module ID/source hash.
- No statement calls expected capacity realised success, smoke output annual
  economics, legacy comparison exact parity without evidence, or the CEM globally
  optimal.
- Domain review confirms the storage, cost, carbon, pipeline and system-boundary
  sections match executed equations.
- README commands work from the supported clean environment using synthetic data.

## Stop condition

Where code and documentation disagree, correct the documentation only if the code
is the accepted scientific implementation. Otherwise open a blocking implementation
issue and withhold the claim; do not normalize an unintended behavior in prose.

## Deliverable

Provide the formal reference, evidence matrix, generated-schema checks, updated
README and a list of deliberately unsupported/deferred capabilities such as DC/AC
network constraints, reserves and full unit commitment.

