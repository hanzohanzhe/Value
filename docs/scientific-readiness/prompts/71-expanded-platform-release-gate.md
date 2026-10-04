# Prompt 71 — Expanded-platform release gate

Execute after the selected subset of Prompts 66 and 68-70 is complete. Prompt 69
may remain an optional experimental capability; do not block a DC/hydrology
extension release merely because AC global optimality is not established. Act as
an independent release engineer and power-system scientific auditor. Implement
no new feature here.

## Objective

Decide whether the extension platform and each installed domain capability are
reproducible, backward compatible and scientifically supported at their claimed
maturity. Keep the accepted Prompt 64 single-node beta independently releasable.

## Frozen comparison set

- canonical Prompt 64 commit and release artifacts;
- representative v2 single-node Studies, snapshots, checkpoints and outputs;
- Prompt 65 toy extension and conformance/security evidence;
- accepted hydrology, DC, AC and/or network-expansion fixtures and reports;
- any new full-year, causal two-year or long-horizon bundles required by the
  actual scientific changes being released.

## Gate sequence

1. **Backward-compatibility gate.** Fresh-install Prompt 64, then upgrade to the
   extension release. Existing v2 projects must retain their frozen graph and
   results; old run bundles remain readable without implicit scientific migration.
2. **Extension isolation gate.** Install, enable, disable and upgrade multiple
   namespaced extensions. Prove conditional roles, parameters, state, artifacts,
   hooks and module resolution do not collide or bypass the one registry.
3. **Hydrology gate.** If Prompt 66 is shipped, run analytical water/energy cases,
   24/168-hour independent checks, data-provenance failures and no-pumped-hydro-
   duplication tests. State separately whether a real UK hydrology path was
   evaluated.
4. **DC network gate.** If Prompt 68 is shipped, pass every analytical, random,
   24/168-hour, mutation and production-invocation comparison. Publish maximum
   nodal balance, KVL, branch-bound, SOC and objective residuals.
5. **AC gate.** If Prompt 69 is shipped, report exact formulation, solver,
   convergence, residual and optimality class. A local/experimental decision must
   remain visible; an unavailable optional solver is not a green validation.
6. **Transmission-CEM gate.** If Prompt 70 is shipped, pass causal next-year
   injection, lineage, budget, planning, cost and carbon reconciliation. Require
   a full annual and causal two-year network case before annual scientific claims.
7. **Long-horizon gate.** Run a new ten-year case only when publishing an
   endogenous hydrology/network investment pathway or when multi-year scientific
   code used by an existing baseline changed. Otherwise reuse Prompt 64 evidence.
8. **Clean-clone and package gate.** Build every advertised extension/runtime from
   locks on supported systems, verify optional dependency licences, install data
   packs/modules transactionally, exercise browser workflows and scan archives.
9. **Claims gate.** Link every claim—single-node, DC, AC, hydrology, network
   expansion, cost, carbon and reproducibility—to immutable evidence. Unsupported
   capabilities must not appear as ready in Studies.

## Required decisions

Issue separate `GO`, `EXPERIMENTAL`, `NO_GO` or `NOT_EVALUATED` decisions for:

- v2 single-node backward compatibility;
- general extension framework;
- run-of-river and reservoir hydrology;
- DC network clearing;
- AC feasibility and AC OPF, separately;
- endogenous transmission expansion;
- each real-data pack used by those capabilities;
- annual and long-horizon scientific baselines.

## Acceptance

- All v2 preserved cases remain scientifically identical and retained Scheme C
  hashes remain unchanged.
- The extension graph is frozen in revisions/snapshots/checkpoints and all
  capability-specific data are validated before execution.
- Required independent/mutation tests can fail and pass for the right reasons.
- Any annual/two-year/ten-year result is complete for its declared chronology and
  passes physical, cost, carbon, lineage and bundle gates.
- Source and optional runtime packages are reproducible from a canonical clean
  commit and documentation distinguishes maturity and information structure.

## Stop conditions

Return `NO_GO` only for the affected capability/product if it lacks reproducible
installation, input provenance, physical closure, independent validation or
truthful claims. Do not invalidate Prompt 64's single-node beta merely because an
optional extension is experimental. Open a new numbered remediation prompt for
any defect; do not fix it inside the gate.

## Deliverables

- cross-version migration/backward-compatibility report;
- capability-by-capability scientific and packaging evidence matrix;
- minimum necessary annual/causal/long-run evidence selected by change impact;
- clean-clone, security, rights and browser results;
- human- and machine-readable Prompt 71 expanded-platform release decision.
