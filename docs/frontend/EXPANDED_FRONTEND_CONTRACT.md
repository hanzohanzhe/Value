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
