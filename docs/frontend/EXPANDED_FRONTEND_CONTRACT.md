# FORCE expanded frontend contract

Status: frozen by Prompt 77 on 20 August 2026  
Contract version: `force.expanded-frontend/v1`  
Target: separate FORCE `0.6.x` expanded-platform private alpha

## Decision

The expanded scientific components are not a second application. They must be
composed through the same `ModuleRegistryV2` used by preflight, snapshots and
the live application. The browser may present catalogue data, collect explicit
choices and render server responses; it must not infer compatibility from names,
duplicate capability rules or calculate scientific results.

At the Prompt 77 freeze, the single-node browser path was executable while the
ordinary browser could not persist expanded selections. Prompts 78–83 have now
closed that composition gap without changing retained Scheme C or a scientific
equation. The browser saves and preflights the same registry-owned module and
extension graph, renders conditional inputs, and reads immutable optional-domain
artifacts. Prompt 84 keeps hydrology workflow-specific `NO_GO` until the ordinary
annual application emits its declared typed hydrology result index.

## Prompt 77 pre-change end-to-end observation

| Stage | Current source of truth | Prompt 77 finding |
| --- | --- | --- |
| Browser draft | `app/page.tsx` (`projectForm`, Study view) | Contains name, years and a fixed module map. No extension selection, extension parameters or maturity acknowledgement. |
| POST and validation | `backend/server.py::validate_project`, `POST /api/projects` | Validates base `DATASET_SLOTS` and calls `MODULE_REGISTRY.validate_selection(selected_modules)` without extension arguments. |
| Revision | `gridform_core/project_revision.py` | Fingerprint can include an extension graph, but only when extension fields reach it. It currently resolves an extension graph independently of the complete module graph. |
| Preflight | `gridform_core/preflight.py::preflight_project` | Already reads `selected_extensions` and `extension_parameters`, activates conditional roles and calls the one registry. |
| Snapshot/resume | `gridform_core/run_snapshot.py` | Already freezes and re-resolves the complete module/extension graph SHA-256. |
| Live execution | `gridform_core/application.py::run_project_application` | Already calls `registry.resolve_selection` with extensions, parameters and bound roles. |
| Results | `backend/server.py` run routes | Market replay, curtailment, planning, ledgers and downloads have APIs. Network, hydrology and expansion evidence is primarily downloadable artifact output. |

This table is retained as the rollback audit. The loss formerly occurred before
save; the current implementation submits those fields and the backend resolves
them through the same registry used by preflight, snapshots and execution.

## Existing scientific catalogue

### Module slots

The registry is authoritative. Required slots are those whose manifests declare
`selection_required`; optional slots are all other registered slots. The current
catalogue contains the established PSM/CEM chain plus optional
`network_expansion`. React must never maintain a second hard-coded slot list.

### Extensions

| Extension | Maturity | Activates | Conditional input |
| --- | --- | --- | --- |
| `force-network-contract-extension` | ready | solver-neutral network contract and topology | buses, branches, asset map and nodal demand; optional contingencies, ratings and candidates |
| `force-ac-data-extension` | experimental | local AC-feasibility input contract | generator P/Q limits, reactive demand and declared active schedule; optional initial voltage |
| `force-hydrology-extension` | experimental | run-of-river and reservoir resources | site catalogue, asset map, both inflow series and reservoir parameters |
| `force-network-expansion-extension` | experimental | network-expansion lifecycle | candidate-corridor JSON and composed `network_expansion` module |

The reference DC PSM is ready only within its declared linear synthetic scope.
The AC component checks a declared active-power schedule; it is not AC OPF.
Hydrology and endogenous transmission expansion remain experimental. Presence in
the catalogue is not selection and does not upgrade scientific maturity.

## Additive browser/API contract

The workspace response gains `frontend_contract_version`, `module_slots` and
`extensions`. A draft-resolution request is the only compatibility authority.

### Draft request

```json
{
  "schema_version": "force.study-draft/v1",
  "data_pack_id": "pack-id",
  "start_year": 2025,
  "end_year": 2034,
  "modules": {"psm": "module-id"},
  "selected_extensions": ["extension-id"],
  "extension_parameters": {"namespace.parameter": "value"},
  "maturity_acknowledgements": {
    "extension-id@version": "force.experimental-ack/v1"
  }
}
```

### Draft-resolution response

```json
{
  "schema_version": "force.study-draft-resolution/v1",
  "valid": false,
  "errors": [{"code": "GF_EXTENSION_DATA_MISSING", "message": "..."}],
  "warnings": [],
  "module_slots": [],
  "compatible_modules": {},
  "active_dataset_slots": [],
  "effective_extension_parameters": {},
  "maturity": {"acknowledgements_required": []},
  "graph_preview": {"graph_sha256": null, "modules": {}, "extension_graph": null}
}
```

Every field is sourced from one of these existing contracts:

- modules and slots: `ModuleManifest` / `ModuleRegistryV2`;
- extensions, roles, parameters, hooks and artifacts: `ExtensionManifest`;
- pack bindings: `force.data-pack/v1` manifest;
- graph identity: `ResolvedModuleGraph.to_dict()`;
- maturity: module `status` and extension `maturity`;
- runtime availability: the existing runtime capability matrix.

Only the browser response envelope, stable UI error codes and explicit
`maturity_acknowledgements` are new. They contain no model calculation.

## Required states

| State | Browser behaviour | Server evidence |
| --- | --- | --- |
| loading | Retain entered draft; mark resolution pending | request in flight |
| empty | Explain first required choice; no implicit extension | absent explicit selection |
| incomplete | List missing required choices and roles | stable error objects |
| incompatible | Disable affected option and show the missing capability/module | registry validation |
| experimental | Require versioned acknowledgement before save/run | manifest maturity plus saved acknowledgement |
| solver missing | Keep choice visible but disabled for execution | runtime capability report |
| data missing | Link each active role to Data; preserve all other choices | active conditional role plus pack binding |
| failed | Keep form values and allow retry | HTTP/error code and previous successful resolution |
| ready | Show exact graph, versions, pack revision and SHA-256 | resolved graph response |

Unknown module slots, extension IDs, parameter names and data roles fail closed.
An old Study with no extension fields means no extension. No file merely present
in a pack may silently activate a domain.

## Interaction wireframes

### Data

```text
Data pack [Research pack v]   Active Study [Draft: DC + hydrology v]
Readiness 29/34   [5 actions]

Base inputs (25)       Network (4 required + 3 optional)       Hydrology (5)
[ready] Demand         [missing] Buses  [upload] [template]    [ready] Site map
[ready] Weather        [ready] Branches [preview]              [missing] Inflow
```

### Modules and extensions

```text
Capabilities: Single node | DC network | AC feasibility (experimental)
Installed extensions
[ready] Network contract   provides ... requires ... [details]
[experimental] Hydrology   data 4/5   acknowledgement required
Dependency graph: PSM -> capability -> extension -> conditional inputs
```

### Study composer

```text
1 Identity -> 2 System domain -> 3 Optional domains -> 4 Model chain -> 5 Review
DC network
  Reference DC PSM [ready]
  Network contract [selected]
Hydrology [selected, experimental acknowledged]
Review: modules, extensions, parameters, roles, information structure, graph SHA
```

### Run readiness

```text
Study graph [sha...]    Data 34/34    Runtime ready
Maturity: DC ready in reference scope; hydrology experimental
[blocking] none   [warnings] 1 acknowledged
[Run bounded check] [Run full chronology]
```

### Results

```text
Overview | Market | Curtailment | Planning | Network | Water | Expansion | Files
Network: nodal price / branch loading / congestion / balance
Water: inflow / generation / storage / spill / boundary state
Expansion: proposals -> admitted -> planning -> commissioned / failed
```

## Stale or contradictory statements

The following are truthful only for a selected single-node Study, not for the
whole expanded candidate, and must be scoped or replaced in Prompt 84:

- Home: “No transmission constraints” in `app/page.tsx`.
- Data: “The current model has no internal transmission layer” in
  `app/page.tsx`.
- Bilingual guide statements that the current product has no DC/AC model.
- Any wording that presents catalogue availability as scientific validation.
- Any AC wording that omits “local feasibility of a declared schedule”.

## Existing result visibility

Typed query APIs already exist for run summaries, comparisons, market period
tables, auction replay, VRE curtailment, planning records and generic artifact
downloads. Carbon/cost ledgers and provenance are downloadable and partly
summarised. Network period evidence, hydrology period evidence and network
expansion history have declared typed artifacts but no coherent bounded browser
query surface. Prompt 83 may add read-only query adapters; it must not reproduce
the scientific calculations in TypeScript.

## Executed impact of Prompts 78–84

Prompt 78 owns the semantic API and revision identity; Prompt 79 renders it.
Prompt 80 activates roles from draft resolution. Prompt 81 wraps the existing
Prompt 65 installation transaction. Prompt 82 previews inputs through existing
adapters. Prompt 83 exposes DC, AC-feasibility and expansion artifacts through
bounded queries and refuses to reconstruct missing hydrology output. Prompt 84
tests these paths and issues capability-specific decisions. Retained Scheme C
was not edited, no second registry was introduced, and old Studies receive no
implicit extension migration.

## P0 result-view additions (2026-10, additive)

The P0 fixes change read models and serialisation only; no ledger writer and no
clearing, investment or accounting calculation was changed for display. All
changes below are additive: an older backend omits the field and the browser
degrades to a state word.

| Resource | Addition |
| --- | --- |
| `/api/runs/{run}/market/dispatch` | Timeline v2: `price_basis`, flow `role` and canonical technology names; per bucket `shortfall_mwh`, `shortfall_upper_mwh`, `shortfall_basis` (`exact` / `lower_bound`), `stress_periods`, `possible_stress_periods` (decision A2) |
| `/api/runs/{run}/market/stress-events` | New: `value.stress-events/v1`, the full year's A2 stress events (contiguous periods in which accepted supply fell short of demand), paged ≤ 200, numeric start-period order; `status=not_recorded` for a ledger without the `stress_event` table. Row-level evidence, so not withheld under Q14 |
| `/api/runs/{run}/market/vre-summary` | `curtailment_semantics`; `event_basis` gains `corrected_unused_vre` (corrected rule set); `unused_vre_events` and `excess_curtailment_events` reported separately; `coverage` |
| `/api/runs/{run}` | `methodology`, `energy_balance_status`, `energy_balance` (incl. `balance_account`, `raw_boundary_status`), `storage_invariant_status`, `validation_gate`, `stress`, `advisories`, `result_publication` (Q14), `publication_blocked` (production gate), `result_coverage` |
| Run `results[].metrics` | Mechanism costs `null` with a status instead of `0.0`; `system_cost_definition_id`, `system_cost_includes_voll`, `operating_cost_voll_gbp`, `voll_gbp_per_mwh`, `ror_hydro_compatibility_capital_gbp` |
| `/api/runs/{run}/results/vre-curtailment` | `status` ∈ `reconciled`, `unavailable`, `withheld`, `invalid`; a Run cancelled or failed before a declared year finished is `unavailable` (`cancelled_before_year_complete` / `failed_before_year_complete`), never `invalid` |
| CSV mapping preview | Request `fx: {eur_per_gbp, fx_basis[, price_year]}`; review `source_sample_rows`, `fx` |

Missing-value rule: a field that is absent, `null` or not computed is rendered
as `—`, `Not recorded`, `Not modelled`, `Not evaluated` or `Not computed`, never
as 0. `invalid` (red) is reserved for self-contradictory evidence; `Withheld`
only for the Q14 rule on doctoral reproduction runs. Field-by-field mapping:
[`EXPANDED_FRONTEND_FIELD_MAP.md`](EXPANDED_FRONTEND_FIELD_MAP.md#result-views-displayed-value---api-field-p0-fixes-2026-10).

The complete P0 API contract change table, including the breaking changes for
direct clients (session header, no CORS, error codes and statuses), is in
[`CHANGELOG.md`](../../CHANGELOG.md), section 0.7.0-alpha.1, "API contract
changes".
