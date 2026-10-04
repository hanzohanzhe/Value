# FORCE Data Workbench design

Date: 21 August 2026

Status: approved after data-construction grilling Q1–Q23 and section-by-section design review

Scope: reproducible discovery, acquisition, compilation, validation and promotion of the official-source data used to build the optional GB zonal network benchmark

## Purpose

Build an in-repository, layered Data Workbench that turns pinned official UK
source revisions into auditable candidate packs and immutable
`force.data-bundle/v1` bundles. The workbench serves both programmers and local
frontend users without moving scientific transformation logic into React or the
model runtime.

The first use case is the fixed-network GB zonal benchmark required by Prompt
98. The architecture must also support later extraction into an independently
deployed data service without changing FORCE Study, Run, zonal-network or data-
bundle contracts.

## Existing context and compatibility boundary

The active implementation line is the `codex/zonal-redispatch-prompt93-106`
worktree. Prompt 93 froze the network design, Prompt 96 added zonal transport
contracts, Prompt 97 added spatial preprocessing, and Prompt 98 has an
uncommitted candidate GB pack builder. Existing work is preserved.

The Data Workbench does not create a second data-pack registry or network
schema. It reuses:

- the `force.zonal-network-pack/v1` contract family in
  `gridform_core/zonal_contracts.py`;
- the `force.data-bundle/v1` archive, validation and atomic-installation path in
  `gridform_core/data_bundle.py`;
- the existing Study-aware data-role resolution and local data-pack installer;
- the existing Prompt 98 entry point as a compatibility facade.

Prompt 98 remains part of the model workstream. It consumes the promoted output
of the separate `DATA-*` workstream. Prompt 99 and later model tasks must never
read raw-source or unsigned candidate files.

## Non-negotiable boundaries

- Do not edit retained Scheme C or change its accepted hashes.
- Do not change PSM, CEM, redispatch or transmission-expansion mathematics.
- Do not make zonal-network roles mandatory for copperplate Studies.
- Do not download or rebuild scientific inputs during model execution.
- Do not silently adopt the latest online data revision.
- Do not silently combine official, academic, community or inferred data.
- Do not call an ETYS electrical cut a physical line or force it into a single
  pairwise DSO connection.
- Do not allow a candidate pack to masquerade as a promoted benchmark.
- Do not allow an incomplete network run to continue silently as copperplate.
- Do not place large raw-source objects or local cache paths in the Git source
  release.
- Do not expose local absolute paths through public service responses or bundle
  metadata.

## Selected architecture

The selected approach is an in-repository layered Data Workbench. It is more
structured than extending the existing monolithic Prompt 98 builder and avoids
the deployment burden of a separate service at this release stage.

```text
Official source registry
        |
Discover and fetch adapters
        |
Immutable content-addressed raw-object store
        |
Dataset-specific scientific compilers
        |
Canonical zonal-network contracts
        |
Validation and human review package
        |
Promoted force.data-bundle/v1
        |
Existing FORCE data-pack installer and runtime
```

### Code and artifact layout

```text
gridform_core/
  data_workbench/
    contracts.py
    registry.py
    discovery.py
    fetch.py
    object_store.py
    service.py
    promotion.py
    reporting.py
    sources/
      uk-network/
        dso-boundaries.source.json
        etys-capabilities.source.json
        etys-geometry.source.json
        desnz-consumption.source.json
        ons-postcodes.source.json
        fes-gsp.source.json
        interconnector-register.source.json
    compilers/
      dso_zones.py
      etys_capabilities.py
      etys_geometry.py
      cut_membership.py
      regional_demand.py
      interconnectors.py
      gb_zonal_pack.py
    validators/
      provenance.py
      rights.py
      geometry.py
      topology.py
      demand.py
      interconnectors.py
      promotion_gate.py

app/features/data-workbench/
backend/data_workbench_api.py
docs/data-construction/
  INDEX.md
  GAP_MATRIX.md
  prompts/
tests/data_workbench/
publication/data-construction/
```

Large local objects live outside Git:

```text
<local-state>/data-workbench/
  raw/sha256/<object-hash>/
  staging/<build-id>/
  candidates/<candidate-id>/
  bundles/<network-pack-id>/
  reports/<report-id>/
```

The existing `gridform_core/gb_zonal_pack_builder.py` remains an import-stable
facade and delegates progressively to the new compiler modules. Its existing
tests remain compatibility gates.

## Stable service boundary and later hosted migration

CLI, local HTTP API and frontend use the same transport-independent service:

```text
discover(request) -> DiscoveryReport
fetch(source_revision) -> RawObjectReceipt
compile(build_request) -> CandidatePack
validate(candidate_id) -> ValidationReport
promote(promotion_request) -> SignedBundleReceipt
```

The public API schema is `force.data-workbench-api/v1`. Request and response
objects contain identifiers, hashes and report links, not local filesystem
paths.

Four storage and governance ports isolate deployment concerns:

```text
SourceRegistry
ObjectStore
JobStore
ApprovalStore
```

The local beta uses source JSON, content-addressed local files, local SQLite
jobs and local approval attestations. A later hosted service may use a registry
database, R2/S3-compatible objects, queued workers and authenticated approvals.
That migration must preserve service DTOs, candidate identity, bundle schemas,
installer behaviour, Study/Run references and the main frontend workflow.

Authentication, remote roles and cryptographic signing belong to the later
hosted deployment. They are not prerequisites for the local Data Workbench.

## Data-object lifecycle

The lifecycle is strictly ordered:

```text
SourceDefinition
  -> SourceRevision
  -> RawObjectReceipt
  -> BuildManifest
  -> CandidatePack
  -> PromotedBundle
```

### SourceDefinition

A Git-tracked declaration of an approved authority, semantic role, catalogue or
landing page, discovery adapter, allowed domains, expected licence and possible
uses. It identifies a source family rather than one downloaded revision.

### SourceRevision

Metadata discovered for one published revision: source and revision IDs,
publication date, landing and download URLs, media type, reported licence,
catalogue metadata, discovery time and one of `new`, `unchanged`, `superseded`
or `unavailable`. Discovery alone does not authorize scientific use.

### RawObjectReceipt

An immutable receipt created after secure acquisition. It records SHA-256,
byte size, media type, final resolved URL, retrieval time, HTTP metadata,
licence snapshot and a content-addressed object-store key. Scientific compilers
consume the hash-pinned object, never an online URL.

### BuildManifest

The complete declared input to a compilation: target contract, raw-object
hashes, compiler identities and versions, CRS transforms, field mappings,
selected years, tolerances, assumptions, manual mapping overrides and optional
parent candidate. Retrieval and wall-clock timestamps do not affect scientific
content identity.

### CandidatePack

An unsigned build with a content-derived candidate ID, BuildManifest hash,
canonical artifact hashes, validation status, candidate inventory, requested
waivers and review-package references. Identical inputs, code and parameters
must produce identical scientific files and candidate identity.

### PromotedBundle

An immutable, approved release with a human version label, candidate ID,
reviewer, approval time, accepted scientific waivers, rights decision, manifest
hash, bundle hash and optional predecessor. A recommended label is
`gb-zonal-benchmark-2026.1`; the content hash remains the authoritative
identity.

The local beta uses `signature_type=local_approval_attestation`, recording the
reviewer, approval time, candidate ID, manifest hash and accepted waivers. This
is a tamper-evident approval record, not a claim of cryptographic identity.

## Candidate inventory

Every discovered or compiled candidate item has one status:

- `ready_for_promotion`;
- `experimental_only`;
- `validation_only`;
- `needs_mapping`;
- `needs_rights_review`;
- `source_unavailable`;
- `rejected`;
- `superseded`.

Each record states its source and version, licence, `usable_for`,
`not_usable_for`, blocking reasons, required actions and affected artifacts.
Candidate data may run only under an explicit experimental-data selection. The
run snapshot and result must expose candidate identity, unresolved assumptions
and the reason that it is not a promoted benchmark.

## Canonical GB zonal bundle

The first bundle contains at least:

```text
manifest.json
rights.json
provenance.json
assumptions.json
zones.geojson
transport_corridors.csv
etys_cutsets.csv
cut_membership.csv
boundary_ratings.csv
boundary_availability.csv
zonal_demand.csv
demand_reconciliation.json
interconnector_assets.csv
interconnector_profile_allocation.csv
asset_zone_map.csv
region_zone_weights.csv
spatial_audit.json
candidate_inventory.json
```

Geometry uses GeoJSON, modest tabular data uses CSV, and metadata, validation
and audit evidence use JSON. The first release does not require PyArrow. The
manifest assigns every member a semantic role, schema version and SHA-256; the
runtime resolves roles rather than hard-coded filenames.

## Source authority and discovery policy

Promoted benchmark evidence is limited to first-party NESO, DESNZ, Ofgem,
DSO/DNO, interconnector-operator and other UK public-authority sources.
Academic, community and generic-web-search results can be reported as
candidates but cannot be merged silently.

The package-resource source registry and purpose-built discovery adapters are authoritative.
Generic web search may propose a new candidate source for human review; it does
not feed the compiler. Discovery can run at any time, but a benchmark changes
only after diff, validation and human promotion. Old bundles remain replayable.

## Dataset-specific compilation

### DSO areas and network zones

The NESO DNO licence-area GeoJSON defines `resource_zone` records for demand,
asset, CEM-allocation and reporting purposes. The compiler preserves the source
EPSG:27700 geometry and produces an EPSG:4326 display copy. It validates IDs,
geometry, overlaps and GB coverage and records any deterministic geometry
repair.

An approved ETYS cut may split a resource zone into `network_zone` records. Each
network zone retains exactly one resource-zone parent. This permits an 18–24
zone computational representation without losing the DSO reporting layer.
Automated sliver merging is not allowed behind an undocumented threshold;
proposed splits and merges appear in the human map review.

### ETYS capability, geometry and cut membership

The first build combines the ETYS 2025 capability workbook with the latest
officially available ETYS boundary GIS, currently labelled ETYS 2024. It parses
all boundary IDs, directions, years, capability and reverse-capability values.
The formal `Capability` value for 2025 is fixed across the 2025–2034 model
horizon; FES flow percentiles are not interpreted as ratings.

Version reconciliation is field-specific. If one official source supplies a
field and the other does not, the available field is retained. If the same
field conflicts, the newer official value wins and both values enter the diff
evidence. Geometry and capacity are different claims and cannot fill each
other. Boundary information extracted from an official report, including B3b
or B14 evidence, records the report version and page and requires review.

Where no reverse capability is published, the candidate mirrors the forward
limit with `reverse_limit_method=symmetric_forward_fallback`. This is a named,
reviewable scientific waiver, never an official reverse rating.

The compiler combines DSO adjacency and ETYS geometry to propose signed
corridor membership. It renders the positive side, negative side, member
corridors and direction. Human approval is required because ETYS boundaries are
electrical cuts, not merely map intersections. Every discovered ETYS boundary
appears in inventory even when it is excluded from the promoted subset.

The first promoted bundle uses fixed ratings. Seasonal or half-hour availability
remains an input interface. NESO 24-month and day-ahead constraint-limit data
remain candidates until their operational codes are mapped and reviewed against
ETYS cuts.

### Regional demand

The base distribution uses DESNZ postcode-level domestic and non-domestic
electricity consumption and ONS Postcode Directory coordinates. Postcodes are
assigned by point-in-polygon to DSO resource zones and, where split, directly to
network zones. Pure administrative-area overlap is not an accepted load proxy.

NESO FES GSP evidence evolves the base spatial distribution:

```text
unnormalised_weight[z,y]
  = base_weight[z]
  * FES[z,y] / FES[z,base_year]

weight[z,y]
  = unnormalised_weight[z,y]
  / sum(unnormalised_weight[*,y])

demand[z,t]
  = FORCE_national_demand[t] * weight[z,year(t)]
```

The FORCE national total and chronology remain unchanged. Each period's zonal
demand must reconcile within `1e-8 MWh`. DSO half-hour measurements are
candidate calibration or validation evidence until a uniform method is
approved. Missing future spatial evidence may produce an explicitly labelled
`static_share_fallback` candidate.

### Interconnectors

The NESO Interconnector Register supplies asset, connection-site, import/export
capability, status and effective-date evidence. Official GSP/substation,
connection and operator sources resolve site coordinates. A point-in-polygon
operation assigns the landing to one network zone.

Evidence preference is official coordinate, official named-site resolution,
operator-supported location, then `inferred_nearest_coast_dso`. The final method
records evidence level, distance and chosen zone. Northern Ireland is excluded
as an internal zone; Irish exchange remains an external signed interconnector.

Asset-level profiles are preferred. A country-level profile may be allocated
among active assets by effective directional capability using
`capacity_weighted_country_split`. The transformation must conserve the country
profile in every period and respect each asset's declared envelope and sign.

## Validation and promotion gates

### Gate 1: source and rights

Validate allowed authority/domain, publication identity, licence,
redistribution decision, URL, retrieval evidence, SHA-256 and byte size. Unknown
rights cannot be waived.

### Gate 2: file and schema

Validate readable and expected file types, sheets, columns, IDs, dates,
directions, geometries and CRS. Reject unsafe archives, path traversal, missing
critical schema and any compilation attempt not pinned to raw-object hashes.
These failures cannot be waived.

### Gate 3: spatial and topology

Validate unique zones, valid geometry, one resource parent per network zone,
valid corridor endpoints, explained connectivity, non-empty and non-dangling
cut membership, direction, one final location per active asset/interconnector,
and exclusion of Northern Ireland from the internal network.

### Gate 4: scientific reconciliation

Validate non-negative yearly demand weights summing to one, half-hour demand
residual no greater than `1e-8 MWh`, unchanged national technology MW after
spatialization, per-period conservation of interconnector-profile allocation,
directional limits, rating and availability ranges, and a reason for every
excluded or remapped record. Unsupported loss cannot be emitted as calculated
zero.

### Gate 5: determinism and regression

Rebuilding with the same hashes, compiler versions and parameters must produce
identical scientific artifacts and candidate ID. Tests cover simple and
overlapping cuts, asymmetric and symmetric-fallback ratings, postcode boundary
mapping, FES weights, asset/country interconnector profiles and deliberately
broken hash, schema, topology, conservation and promotion cases.

### Gate 6: owner review

The reviewer sees source, geometry, capability, weight and mapping changes from
the prior bundle; candidate inventory; maps; reconciliations; rights; and all
assumptions. Mechanical failures disable promotion. Named scientific waivers,
including symmetric reverse limits, capacity-weighted country splits, nearest-
coast placement and static shares, may be accepted explicitly.

Promotion is atomic. The backend rebuilds or revalidates the candidate hash
before installing the new immutable bundle and does not alter an existing
bundle on failure.

## Failure behaviour

- Discovery failure leaves installed bundles usable and reports source
  unavailability.
- Interrupted fetches never overwrite verified objects and leave no usable
  partial receipt.
- Compilation failure preserves the BuildManifest, raw hashes, structured
  error and log.
- Failed validation leaves the candidate isolated.
- Failed promotion leaves the formal bundle index unchanged.
- An incomplete network pack fails model preflight before solver invocation.
- The UI may create a separate copperplate rerun referencing the failed network
  run; it never mutates or silently downgrades that run.

## Human and machine reports

Every build produces source discovery, candidate inventory, validation, version
diff, rights and scientific-assumption JSON, plus a human `review_report.md`,
maps and reconciliation tables. The report front page states which items are
promotion-ready, what remains isolated, what each candidate can be used for,
why it is blocked and the action required for promotion.

## CLI, API and frontend

The CLI exposes `discover`, `fetch`, `compile`, `validate`, `candidates`,
`promote`, `sources`, `diff`, `report`, `export` and `freshness`. Detailed
artifacts are written to the report store while the console prints a compact
summary.

The local API exposes versioned source, revision, job, candidate, report and
bundle resources under `/api/data-workbench/v1`. Discover, fetch, compile and
validate are background jobs with structured progress and safe cancellation.
Promotion requests contain candidate hash, version, reviewer and accepted
waivers; the backend revalidates rather than trusting the browser.

The existing Data page gains four views:

1. Installed packs;
2. Official sources;
3. Build benchmark;
4. Candidates and review.

The build wizard performs source selection, discovery, fetch, compile and
validation. The review view shows differences, maps, reconciliation, rights and
waivers before explicit promotion. Candidates may be installed only under a
visibly experimental identity and cannot overwrite a formal bundle.

React displays backend-generated evidence and sends commands. It never performs
GIS intersection, demand allocation, capability choice, profile splitting,
hashing or scientific validation.

## Testing strategy

Unit tests cover each registry, lifecycle, compiler, validator and waiver rule.
Mutation tests prove that broken hashes, rights, geometry, corridors, cuts,
ratings, demand, interconnectors and unauthorized promotion fail. A frozen
official sample plus synthetic fixtures exercises the full
discover/fetch/compile/validate/promote/install chain without live-network
dependency.

A separate real-data gate constructs the local official candidate and audits
DSO versions, ETYS reconciliation, postcode coverage, FES weights,
interconnector locations, all fallbacks and deterministic rebuilds. Browser
tests exercise source inspection, job progress, cancellation, candidate review,
experimental install and promotion gating.

Final regression verifies retained Scheme C hashes, copperplate independence,
Prompt 96–98 compatibility, atomic bundle installation, candidate rejection by
model preflight, offline runtime, portable paths and release-data rights.

Ordinary CI uses frozen fixtures. A separate manual or scheduled freshness
audit accesses live official portals and reports revisions without changing a
benchmark.

## Independent DATA prompt workstream

The model Prompt index remains unchanged. Data construction uses:

1. `DATA-01`: lifecycle contracts, service API, state layout and Prompt 98
   compatibility boundary;
2. `DATA-02`: official source registry, discovery adapters and freshness audit;
3. `DATA-03`: secure fetch, content-addressed object store, rights and
   provenance receipts;
4. `DATA-04`: DSO and ETYS compilers plus version reconciliation;
5. `DATA-05`: DESNZ/ONS/FES regional-demand compiler;
6. `DATA-06`: interconnector evidence and profile-allocation compiler;
7. `DATA-07`: zone/corridor/cut candidate construction and review map;
8. `DATA-08`: validation matrix, reports, waivers and atomic promotion;
9. `DATA-09`: CLI, local background-job API and cancellation;
10. `DATA-10`: frontend, end-to-end official build, Prompt 98 handoff and
    release audit.

Each prompt defines scope, prohibited changes, input contracts, failing tests,
implementation, acceptance gate, failure artifacts and Prompt 98 impact. A
prompt starts only after its predecessor passes.

## Git and execution sequence

Before implementation, inspect and test the current uncommitted Prompt 98 work,
then save it as an explicit Git WIP checkpoint. Create a dedicated
`codex/data-workbench` worktree from that checkpoint. Execute and commit each
`DATA-*` prompt separately. After `DATA-10`, run combined model/data regression
before choosing how to integrate the branch back into the zonal-redispatch
workstream.

Git commits, not ZIP copies, are the rollback authority. The checkpoint does
not imply that unfinished Prompt 98 scientific output is approved.

## Acceptance outcome

The workstream is complete when a local user can discover official revisions,
fetch and pin permitted objects, deterministically compile and validate the GB
zonal candidate, understand every isolated item and approximation, explicitly
promote an accepted immutable bundle, install it through the existing data-pack
path and reproduce the same scientific hashes offline. Completion of the data
workstream allows Prompt 98 to proceed; it does not by itself validate the
zonal redispatch solver or a ten-year network result.
