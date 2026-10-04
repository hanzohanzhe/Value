# Zonal Solver Contract v1 Design

**Status:** Approved design, pending implementation

**Date:** 23 August 2026

**Scope:** Experimental FORCE zonal transmission and redispatch module only

## Purpose

The zonal redispatch solver uses a four-level lexicographic linear programme:

1. minimise redispatch bid cost in GBP;
2. minimise absolute deviation from the national schedule in MWh;
3. minimise storage and boundary-flow throughput in MWh;
4. apply a stable-key objective to select a reproducible asset-level solution.

Exact floating-point equality between consecutive objective optima is not a
portable solver contract. Real 24-hour production testing showed that a
feasible HiGHS primary optimum can become numerically infeasible when copied as
an exact equality into a later phase. The public scientific contract is
therefore **numerical lexicographic optimality**: a later phase may degrade an
earlier objective only within a declared, unit-aware, solver-derived one-sided
tolerance. Physical feasibility, energy balance, state of charge, transfer
capacity and settlement identities are not relaxed.

The existing copperplate PSM and CEM are outside this change.

## Baseline solver identity

The built-in baseline is:

- SciPy `1.8.1`;
- `scipy.optimize.linprog` method `highs-ds`;
- primal feasibility tolerance `1e-9`;
- dual feasibility tolerance `1e-9`;
- presolve enabled;
- no automatic fallback to `highs-ipm`, another solver or the copperplate
  model.

The exact SciPy and embedded HiGHS identities must be recorded with each run.
Other solver-stack versions may execute, but they are labelled
`solver_stack_not_yet_validated` until they pass the random, mutation, 24-hour
and 168-hour gates. A baseline upgrade requires the same gates before the new
stack receives a validated label.

## One-sided lexicographic tolerance

For each locked objective level `k`, evaluated at its optimum `x*`:

```text
U_k     = sum(abs(c_i * x_i*))
gamma_n = n * epsilon / (1 - n * epsilon)
tau_k   = max(
    unit_floor_k,
    solver_tolerance_k * max(1, U_k),
    gamma_n * U_k,
)
```

where:

- `n` is the number of non-zero objective terms;
- `epsilon` is the machine floating-point precision;
- `solver_tolerance_k` is the largest active primal, dual or IPM tolerance for
  the selected method;
- the GBP floor is `1e-8 GBP`;
- the MWh floor is `1e-9 MWh`.

The optimum is imposed on later minimisation phases as a one-sided inequality:

```text
objective_k(x) <= objective_k(x*) + tau_k
```

The final degradation is recomputed from the returned final solution:

```text
d_k = max(0, objective_k(x_final) - objective_k(x*))
```

Every locked level must satisfy `d_k <= tau_k`. The stable-key objective is the
last phase, so it is not itself locked for a later phase. NaN, infinity, an
invalid term count or an uncomputable absolute-term scale is a hard failure.
No empirical multiplier, symmetric relaxation or hidden rounding is permitted.

## Validation and execution ceilings

The built-in validated ceilings are:

| Objective | Unit | Validated ceiling per half-hour |
| --- | --- | ---: |
| Redispatch bid cost | GBP | `0.01` |
| Absolute schedule deviation | MWh | `0.001` |
| Physical throughput | MWh | `0.001` |

The immutable platform execution ceilings are:

| Objective | Unit | Absolute ceiling per half-hour |
| --- | --- | ---: |
| Redispatch bid cost | GBP | `0.10` |
| Absolute schedule deviation | MWh | `0.01` |
| Physical throughput | MWh | `0.01` |

Classification uses the greater of the computed tolerance and the observed
degradation as a fraction of the validated ceiling:

- up to 10%: `GO`;
- above 10% and up to 100%: `GO_WITH_NUMERICAL_WARNING`, while retaining the
  built-in solver-validated label;
- above 100% and up to the absolute execution ceiling: execution continues as
  `COMPLETED_WITH_NUMERICAL_WARNING`, but the run and its downstream study lose
  the solver-validated label and the Prompt 107 release gate is `NO-GO`;
- above the absolute execution ceiling: hard failure with the declared input
  and solver evidence preserved.

When a PSM year completes above the validated ceiling but below the absolute
ceiling, CEM investment and planning continue. The numerical warning and
unvalidated status propagate to every later year and the whole study.

The annual summary records, by objective level, the maximum computed tolerance,
maximum observed degradation, number of periods above 10%, number above 100%
and cumulative absolute degradation. There is no separate annual failure line;
the worst half-hour determines the validation state.

## Advanced settings and project identity

Advanced settings may select:

- `highs-ds`, `highs-ipm` or `highs`;
- primal and dual feasibility tolerances from `1e-10` through `1e-7`;
- IPM optimality tolerance from `1e-12` through `1e-7`;
- validated ceilings and the warning fraction, provided they remain below the
  immutable platform execution ceilings.

The built-in defaults remain read-only as the validated baseline. Saving any
non-default choice requires one explicit acknowledgement. The UI states that
the change creates a new project revision and removes the built-in
solver-validated label. The run itself does not display repeated confirmation
dialogs.

Every solver-contract field participates in the study fingerprint, checkpoint
identity and exported study definition. Old study files remain byte-for-byte
unchanged. A study without solver-contract fields is migrated by deriving a new
execution copy, recording the source hash and migration reason, and recomputing
the project revision. Defaults are never inserted silently into an old identity.

## Module and platform contracts

The built-in zonal module advances from `1.1.0` to `1.2.0`. The new version
declares:

- solver-contract schema and defaults;
- numerical lexicographic semantics;
- validation and execution ceilings;
- advanced-setting bounds;
- v7 solver-evidence capability.

The module remains **Experimental**, is not the default PSM and is validated
only under the stated UK benchmark contract. It is not a security analysis,
full power-flow model or transmission-expansion module. Copperplate remains the
default FORCE study mode.

The stable-key coefficients and ordering rule are fixed and documented for the
built-in module. Changing them requires a new module version.

Third-party PSM or transmission modules may use different optimisers and
solver contracts. They must emit conforming v7 solver evidence, and the platform
always enforces energy, SOC, capacity, settlement and ledger validators. A
third-party module receives a validated label only after passing its declared
independent gates.

## Evidence and storage

New runs use ledger schema v7. Readers retain read-only compatibility with v5
and v6; old completed databases are never rewritten. v7 adds a normalised
`network_solver_diagnostics` table with one row per period and locked phase.

Required columns are:

- run, year, period and phase identifiers;
- module and solver-contract versions;
- SciPy and embedded HiGHS identities;
- method, presolve and active solver tolerances;
- objective unit, optimum and achieved final value;
- observed degradation and computed tolerance;
- warning, validated and absolute ceilings;
- non-zero term count and absolute-term scale;
- validation class, error code and declared-input SHA-256.

The same evidence is available in the detailed JSON export. SQLite and JSON are
the authoritative detailed records; the frontend does not render every solver
row.

## Frontend and documentation

The run summary displays:

- solver method and solver-contract version;
- solver-stack validation status;
- maximum tolerance-ceiling utilisation;
- count of warning and unvalidated periods;
- a direct link to detailed export evidence.

The advanced-settings acknowledgement explains the project-revision and
validation consequences before saving. The model handbook documents the four
objectives, one-sided formula, default solver settings, allowed advanced ranges,
status thresholds, CEM propagation and the distinction between numerical and
physical tolerances. The module-development guide documents how an external
module declares an alternative solver contract and v7 evidence.

## Error handling

The module never silently changes the selected solver or network model. Solver
failure, non-finite diagnostics, post-solve lock violation or absolute-ceiling
violation preserves:

- the complete declared input;
- module, project, data-pack and network-pack identities;
- solver settings and environment;
- every completed phase optimum and tolerance;
- the raw solver status and message.

The failed zonal study remains failed. A user may explicitly create a separate
copperplate or alternative-solver study.

## Verification sequence

Implementation follows test-driven development and resumes Task 10 only after:

1. formula, unit, range, classification and fingerprint unit tests;
2. cancellation, bound-noise and multi-phase analytical regressions;
3. material primary, secondary and physical degradation mutations;
4. deterministic random convex cases;
5. v5/v6 read compatibility and v7 write/round-trip tests;
6. frontend advanced-setting and status tests;
7. documentation and source-release consistency checks;
8. exact replay of the two preserved 24-hour failures;
9. complete affected Python and frontend suites.

The production gate then starts again from a fresh output root in this order:

1. matched two-period copperplate and zonal smoke;
2. exact failed periods;
3. matched 24-hour cases;
4. matched 168-hour cases;
5. matched complete 2025 cases;
6. causal matched 2025–2026 cases only after annual GO.

Any earlier failure prevents later gates. Prompt 105 ten-year studies remain
outside this design and Task 10.

## Acceptance criteria

The design is accepted only when:

- all public solver settings are fingerprinted and auditable;
- no old study or database is modified;
- physical and ledger validators remain unchanged in strictness;
- the final solution respects every one-sided objective cap;
- warning and validation states propagate through PSM, CEM, exports and UI;
- the v7 evidence reconciles with JSON and annual summaries;
- default and custom solver contracts are visibly distinct;
- the complete production sequence reaches the declared gate or reports a
  truthful, input-preserving blocker.
