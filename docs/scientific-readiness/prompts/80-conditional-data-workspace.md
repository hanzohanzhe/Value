# Prompt 80 — Conditional Data workspace for expanded Studies

Execute after Prompt 79. Reuse Prompt 61 data-bundle installation, current
object store, binding revisions, rights ledger and upload safety controls. Read
the Prompt 65–70 conditional role manifests and every shipped adapter. Act as a
research-data UX architect and power-system data-contract engineer.

## Objective

Make Data show the exact base and conditional inputs required by a selected
draft or saved Study. Do not build a second pack format, weaken rights checks or
claim that every accepted file extension has a built-in parser.

## Work

1. Add a Study-context selector and group roles as Base PSM, Base CEM, Network,
   AC feasibility, Hydrology and Network expansion. Source the active list from
   Prompt 78 draft resolution.
2. For every role show owner extension, capability, required/optional state,
   accepted and actually supported formats, units, time semantics, schema,
   source/provenance, licence, SHA-256, binding revision and validation result.
3. Retain Prompt 61's full-bundle installer and atomic per-binding replacement.
   A failed conditional upload must not change the previous valid binding or
   another Study's frozen revision.
4. Offer downloadable CSV/JSON templates and compact column/schema examples
   generated from canonical contracts for:
   - buses, branches, asset map and nodal demand;
   - AC generator/PQ, reactive demand and declared active schedule;
   - hydrological sites, asset-site mapping, run-of-river inflow, reservoir
     inflow and reservoir parameters;
   - transmission-expansion candidates.
5. Add server-side preview/validation summaries instead of loading full annual
   tables into the browser. Include timestamp coverage, duplicates, units,
   missing IDs, bus/site references and base-demand reconciliation.
6. Explain that pumped hydro remains storage and must not be uploaded as a
   conventional reservoir-hydro asset. Explain that imports remain boundary
   offers rather than branches.
7. Provide a deterministic `Download missing-input checklist` for collaboration
   with a data steward. It contains contracts and statuses, never embedded
   private data.

## Acceptance

Changing the draft capability graph immediately recalculates required roles
without mutating the pack. DC, AC, hydrology and expansion fixtures can be
completed through ordinary browser uploads or one Prompt 61 bundle. Missing,
mis-mapped, wrong-unit, wrong-timezone, dangling-endpoint, duplicate and
rights-unacknowledged cases fail with corrective actions. Base single-node packs
remain 25-role-ready when no extension is selected.

Stop if the UI must guess a column mapping, duplicate adapter code in
TypeScript, read an absolute source path, or mark an unsupported parser as ready.

