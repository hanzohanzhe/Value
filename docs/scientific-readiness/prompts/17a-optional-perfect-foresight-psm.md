# Prompt 17A - Optional perfect-foresight storage co-optimization PSM

Continue only after scientific Prompts 12, 15 and 16 are accepted. Read the
actual production call path, `gridform_core/v2/interfaces.py`, the PSM contracts,
module manifests, storage technology catalogue, cost ledger and the published
dynamic annual storage-cost implementation before editing. Act as a power-system
optimization architect.

Apply the preservation boundary in `docs/scientific-readiness/README.md`. Never
edit retained Scheme C source, fixtures, installed UK data packs, historical run
bundles or the published FORCE dynamic storage-cost equations. Work only in the
copied modular implementation, public contracts, new modules, UI and tests.

## Objective

Add a genuinely selectable perfect-foresight linear-dispatch PSM that centrally
co-optimizes thermal generation, VRE use/curtailment, imports, storage charging,
storage discharging, state of charge and involuntary demand curtailment over the
chosen chronological horizon.

This is a counterfactual market formulation, not a correction to FORCE. The
published FORCE dynamic annual-average recovery policy remains the default
storage offer rule for the FORCE bid-at-cost PSM. A project must select one of
two explicit participation regimes:

- `force_agent_bidding`: storage submits offers using the selected published,
  legacy or user-defined storage-cost policy;
- `perfect_foresight_cooptimization`: the system optimizer controls storage and
  no storage offer-cost policy is applied.

Never silently translate the published dynamic storage bid into an optimizer
objective and never label perfect foresight as a storage-pricing formula.

## Non-duplication boundary

- Reuse the accepted `PSMEngine`/manifest resolution and native annual
  orchestrator from Prompt 12. Do not create a second runner or call the
  compatibility kernel and replay its result.
- Reuse canonical data adapters, storage catalogue, annual cost ledger, market
  artifact writer and project revision fingerprints.
- Do not duplicate pumped storage as reservoir hydro. Existing pumped-hydro
  assets enter through the same storage asset contract with their own catalogue
  efficiencies and no battery cycle-depreciation term.
- Keep capacity expansion and the planning pipeline unchanged. The chosen PSM
  supplies the same typed `MarketYearResult` to the existing CEM chain.

## Implement

1. **Make the PSM input sufficient and typed.** Audit whether `PSMInput` exposes
   chronological demand, availability, import limits/costs, asset marginal
   costs, storage power/energy limits, efficiencies and initial/terminal SOC.
   Add implementation-neutral typed contracts or immutable artifact references
   where required. Do not hide required arrays in undocumented `extensions`.
   Version any incompatible contract change and provide an explicit adapter for
   accepted v2 modules.

2. **Add the module and manifest.** Implement a new external-style PSM module
   such as `force-perfect-foresight-lp` through the same public PSM contract used
   by website projects. Declare solver/formulation version, determinism,
   capabilities, required inputs, terminal-SOC treatment and source hash. A
   missing solver or incompatible data pack must fail in preflight; it must never
   fall back to FORCE or Scheme C.

3. **Use a transparent open optimization backend.** Select an actively
   maintained open-source LP backend that supports the locked Python 3.10
   environment. Pin its package and solver versions, record the license and
   expose solver status, objective, primal feasibility, dual availability and
   tolerances in the run bundle. Keep the formulation independent of any
   optional PyPSA installation.

4. **Implement the chronological LP in consistent energy units.** For each
   period, enforce at minimum:

   - demand balance including generation, VRE, imports, storage charge and
     discharge, curtailment and a separately priced blackout/slack variable;
   - thermal, VRE and import availability/capacity limits;
   - storage charge/discharge power limits converted with `period_hours`;
   - `SOC[t] = SOC[t-1] + eta_charge * charge[t] - discharge[t] / eta_discharge`;
   - technology-specific energy capacity and SOC bounds;
   - the declared charge/discharge exclusivity treatment without inventing
     unrecorded capacity. Do not claim that separate continuous power bounds or
     a shared-converter inequality mathematically prohibit simultaneous charge
     and discharge. Either prove and preflight the convex conditions under which
     simultaneity is strictly dominated (including free curtailment, efficiency
     loss and admissible cost signs), or expose a separately versioned MILP mode
     with a binary operating state;
   - one versioned terminal rule: fixed terminal SOC, cyclic SOC, or an explicit
     terminal value. The project fingerprint must change when this rule changes.

5. **Define the objective without double counting.** Minimize physical variable
   resource cost plus VOLL and any catalogue-backed variable degradation cost.
   Annualized project CAPEX and FOM remain in the reconciled annual system-cost
   ledger and CEM economics; do not also charge them as marginal dispatch cost.
   Battery cycle degradation may enter only once. Pumped hydro has no battery
   cycle-depreciation component. State precisely whether market prices are LP
   balance duals and distinguish resource cost from market payments.

6. **Make selection understandable in the frontend.** Add a `Market
   formulation` control with `FORCE agent bidding` as the existing/default
   research baseline and `Perfect-foresight co-optimization` as an optional
   counterfactual. Show `Storage offer rule` only for agent bidding. When perfect
   foresight is selected, display `Not applicable - storage is centrally
   co-optimized`; do not retain a hidden storage-cost selection in the resolved
   project. Filter incompatible module/data combinations before launch.

7. **Preserve auditability and speed.** Return the normal annual summary and the
   existing bounded market artifact. Put detailed primal/dual/constraint
   diagnostics in machine-readable artifacts, not the main run card. Include the
   selected formulation, solver, horizon, terminal rule and objective components
   in provenance. If a MILP mode is used, do not report an LP balance dual as a
   clearing price unless it is obtained by a documented post-solve pricing LP;
   otherwise mark the price unavailable.

8. **Document extension.** Add one minimal solver-backed example PSM outside the
   built-in FORCE package showing how another modeller can implement the public
   contract. The example must use synthetic data and must not import retained
   Scheme C internals.

## Tests and acceptance

- Analytical one-, two- and four-period cases cover thermal/VRE/import merit
  order, curtailment, scarcity, charging losses, discharging losses, full/empty
  SOC, power limits, energy limits and terminal SOC.
- A 24-hour arbitrage case and a 168-hour chronological case solve with energy
  balance and SOC residuals within declared tolerances.
- Separate battery and pumped-hydro fixtures prove technology-specific
  efficiencies and prove that pumped hydro receives no battery cycle wear.
- A no-arbitrage price path leaves storage idle except where terminal rules
  require movement. A known low/high price path reaches the analytical optimum.
- Every convex-LP fixture satisfies the declared no-simultaneous-operation
  conditions and reports zero simultaneous throughput within tolerance. A
  deliberately incompatible negative-cost fixture must be rejected by preflight
  or handled by the explicit MILP mode.
- Infeasible input without an allowed slack fails clearly; an enabled blackout
  variable is bounded and charged exactly once at the declared VOLL.
- Selecting the new module in the real website/application service changes the
  resolved module ID, source hash, execution evidence and dispatch. Selecting
  FORCE still executes the published agent-bidding path unchanged.
- Storage offer-rule controls are rejected as incompatible with perfect
  foresight, rather than ignored silently.
- Two-period and two-year smoke runs traverse PSM -> investment -> caps ->
  planning -> next-year state through the native modular orchestrator.
- Retained-source hashes and the accepted published storage-policy tests remain
  byte/numerically unchanged.

## Stop conditions

- If Prompt 12 has not made the selected `PSMEngine.run()` the real production
  call path, stop and return `BLOCKED_BY_PROMPT_12`; do not wire the new solver
  around the public contract.
- If required chronological inputs cannot be represented without an incompatible
  contract change, version the contract and stop before pretending v2 accepted
  data it did not contain.
- If solver termination is non-optimal, infeasible, unbounded or numerically
  suspect, publish no scientific economics and never substitute a previous run.

## Deliverable

Provide the mathematical formulation, typed input/output changes, module
manifest, solver/license/version record, UI compatibility rules, analytical
fixtures, 24-hour and 168-hour evidence, two-year smoke result, retained-hash
result and a concise statement distinguishing published FORCE bidding from the
perfect-foresight counterfactual.
