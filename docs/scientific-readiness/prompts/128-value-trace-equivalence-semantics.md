# Prompt 128 — context-aware VALUE trace-equivalence semantics

## Diagnosis

The Prompt 127 summary and full fixtures produced byte-identical physical and
economic science tables, but their context-bound rolling science roots differed.
This is expected provenance behaviour: the immutable run context records the
distinct run ID and trace profile, while `solver_declaration_link` records a
declared-input SHA derived from that run-specific input. A context-bound root is
therefore not a cross-run result hash.

The observed numerical discrepancy is exactly zero. Nine of ten common science
tables are row-identical; the only differing field is the run-specific
`solver_declaration_link.declared_input_sha256`.

## Goal

Make the bounded trace-equivalence gate compare scientific results rather than
requiring two differently identified runs to have the same provenance root.

## Locked scope

- Change only the Prompt 127 verification runner, its focused tests and reports.
- Do not change VALUE model code, market-ledger code, schemas, PSM, zonal LP,
  SOC, CEM, data or results.
- Require both ledgers to validate independently.
- Require exact row equality for period summary, dispatch, storage,
  redispatch, zonal accounting, VRE curtailment, demand alignment, zone and
  boundary summaries. Do not use a percentage or numerical tolerance.
- Permit `solver_declaration_link.declared_input_sha256` to differ only when all
  other solver-link fields are identical and the run identities/trace profiles
  are explicitly different.
- Retain and report both context-bound science roots and evidence roots; label
  them as expected provenance differences rather than rewriting either root.
- Any physical, economic, curtailment, SOC or solver-status difference fails.

## Acceptance checks

1. The retained Prompt 127 summary/full artifacts pass trace equivalence with
   `maximum_absolute_numeric_difference=0.0` and an explicit provenance-only
   difference record.
2. A one-micro-unit change in any scientific numeric table fails.
3. An unexpected solver-link field change fails.
4. The runner proceeds to failure/preflight only after this corrected trace gate
   passes.
5. Final bounded reports remain fail-closed and do not claim that a production
   annual or ten-year run occurred.

## Bounded execution result

The focused Prompt 127 suite passes 12/12. It proves exact acceptance for
distinct summary/full run contexts, rejection of a `0.000001` physical change,
rejection of `solver_status` and other solver-link changes, independent
validator enforcement, and replacement of only Prompt 125's invalid
cross-context root-equality audit condition.
It also preserves Prompt 125's bounded-run-success and common-result guards and
labels downstream evidence that was not executed as `NOT RUN`.

The fresh bounded execution remained fail-closed. The 48-period literal,
336-period growth and two-year state-coupling gates passed. The trace comparison
then recorded exact equality across all nine locked scientific tables,
`maximum_absolute_numeric_difference=0.0`, identical solver-link fields other
than `declared_input_sha256`, distinct run IDs and summary/full trace profiles,
and both unchanged science/evidence roots labelled `context_bound`.

The trace gate nevertheless failed because the independently validated full
ledger reported 96 evidence-chain errors: 48 period evidence-projection
mismatches, 47 previous-evidence mismatches and one annual evidence-root
mismatch. The summary ledger validated. As required, the runner stopped there;
failure/preflight, annual, two-full-year production and ten-year production were
not run, and no model repair was attempted.
