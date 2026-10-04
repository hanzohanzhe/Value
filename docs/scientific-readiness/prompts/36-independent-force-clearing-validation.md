# Prompt 36 — Independent validation of actual FORCE clearing

Continue only after Prompt 35 is accepted. Reuse the Prompt 17B PuLP/CBC oracle;
do not call FORCE implementation code from the oracle.

## Objective

Read the declared-input artifact and independently formulate the same information
structure and bid-at-cost constraints used by FORCE. Validate thermal, VRE,
boundary imports and storage competition, energy balance, SOC, efficiency, power
and energy bounds over deterministic 24-hour and 168-hour traces.

## Acceptance

- FORCE is invoked through the public registered module and its source hash is
  recorded.
- The independent engine reads only the declared contract.
- Feasibility, objective, dispatch aggregates, SOC and shortage/curtailment agree
  within declared tolerances; equal-price alternative optima are handled explicitly.
- A period-by-period FORCE information structure is not compared with an oracle
  that has undeclared future knowledge.
- Return `FORCE_CLEARING_INDEPENDENTLY_VALIDATED` only when all required cases pass.

