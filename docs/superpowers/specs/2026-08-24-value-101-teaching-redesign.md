# VALUE 101 teaching redesign

Date: 24 August 2026

Status: approved after decision grilling Q1-Q50

Supersedes: the public-facing Castle 101 name and the fixed-click teaching route

Builds on: `2026-08-20-castle-101-teaching-design.md` and `2026-08-21-zonal-redispatch-network-design.md`

## Purpose

VALUE 101 is the first-use route through the real VALUE application. In about
30 minutes, a new user must be able to run a baseline, replace one data pack,
replace one scientific module, and explain why the results differ. It must
teach composition, not merely launch a preconfigured script.

VALUE 101 is not a second frontend, a second solver, a set of precomputed result
cards, or a simplified kernel. It uses the production data contracts, module
registry, immutable Study revisions, run service, PSM-CEM lifecycle, SQLite
evidence store and artifact-backed result views. Its simplifications are
synthetic inputs, two short teaching clocks and one deterministic planning
timing override.

## Product identity and clean rename

The public name is:

> **VALUE 101 — a synthetic GB-style teaching system**

The first external build has no Castle users. Do not add compatibility aliases
or migration machinery. Rename public and internal teaching identifiers
cleanly:

- installer: `VALUE-101-Setup.exe`;
- desktop and Start menu product: `VALUE 101`;
- local application root: `%LOCALAPPDATA%/VALUE-101`;
- baseline pack: `value-101-baseline-v1`;
- variants: `value-101-windy-v1` and `value-101-high-demand-v1`;
- canonical Study: `value-101-baseline`;
- API route: `/api/tutorials/value-101`;
- browser progress key: `value.101.progress.v1`.

Old Castle test state is removed manually on the developer machine. The
released installer must not scan, migrate or delete an old Castle directory.

## Scientific boundary

Every VALUE 101 object is synthetic and CC0-1.0. The pack is GB-style because
it uses familiar technologies, GBP units, European boundary offers and
REPD-shaped planning records. It is not British evidence. Its manifest must say:

- `country=SYNTHETIC`;
- `timezone=UTC`;
- `teaching_only=true`;
- `annual_economics_eligible=false`;
- `scientific_baseline_eligible=false`;
- `period_hours=0.5`;
- `periods_per_year=48`.

Each of 2025 and 2026 contains 48 half-hours. The tutorial executes the normal
2025 PSM, investment/cap/planning chain, state transition and 2026 PSM. It sets
`planning.defer_spread_years=0` only so that the named teaching project can be
observed within the two-year course.

Teaching results use names such as `teaching-window cost`, `teaching-window
emissions` and `cost per served MWh`. They are never annualised in the browser
and are never labelled annual GB system cost, annual carbon intensity or a
national capacity pathway.

## First-use information architecture

The same VALUE application provides four home-page entries:

1. **Start VALUE 101**;
2. **Build a Study**;
3. **Open a saved Study**;
4. **Add data or modules**.

The normal product surface presents the accepted single-node model and the
fixed-network constraint/redispatch capability. AC feasibility does not appear
on Home, in the ordinary registry response, in the Study composer, installer,
README, user manuals or public capability claims. Its source and direct tests
may remain under an explicitly internal experimental path and require manual
developer activation. The public interface must not imply AC-OPF support.

The default Home page does not lead with implementation maturity tables. Those
belong in a separate developer/release-evidence view.

## Teaching route

The course recommends, but does not hard-lock, this order:

1. learn Data, Modules, Study, Run and Results;
2. inspect and run the standard baseline;
3. create and run one data variant;
4. create and run one storage-pricing variant;
5. compare the three controlled Studies;
6. open **Build from VALUE 101**;
7. optionally complete the three-zone network-constraint exercise.

Every action states what it will create or change before the user selects it.
Creating a Study and launching a Run remain separate explicit actions. The
browser never auto-runs after a data or module selection.

### Baseline transparency

Before the first run, show the selected pack and the entire annual model chain
in execution order. Each module card has two levels:

- plain language: purpose, current method and why the step exists;
- technical disclosure: module ID, version, contract, inputs, outputs and source
  location.

The standard baseline is visible but locked so that all learners obtain the
same comparison anchor. It selects the same production implementations used by
the current VALUE teaching path:

- PSM: `scheme-c-psm`;
- storage pricing: `dynamic-annual-storage-cost`;
- investment: `agent-investment`;
- VRE expansion cap: `vre-expansion-cap`;
- storage expansion cap: `storage-expansion-scheme-c`;
- planning: `planning-pipeline`;
- transition: `scheme-c-state-transition`.

There is no tutorial-only scientific implementation behind those labels.

## Controlled data experiment

Generate three complete, independently installable data packs. Each contains
all 25 required semantic roles, a complete manifest, units, source and
transformation records, SHA-256 values and a CC0 dedication.

1. **VALUE 101 — Baseline** is the accepted deterministic teaching system.
2. **VALUE 101 — Windy** changes only wind availability. Every baseline wind
   availability value is multiplied by `1.35` and clipped to `1.0`.
3. **VALUE 101 — High demand** changes only real and forecast demand. Both are
   multiplied by `1.20` in every period.

Fleet, costs, solar, import envelopes, planning records, model parameters and
every unrelated byte-level scientific table remain identical where the
controlled definition requires identity. A machine-readable derivation record
names the parent pack, transformation, affected roles and unchanged-role hash
comparison.

The learner selects either Windy or High demand and explicitly creates a new
immutable Study revision. VALUE copies the baseline years, parameters, runtime
settings and modules. The UI shows the one intended changed dimension before
saving.

## Controlled module experiment

The first module experiment changes only the storage-pricing slot:

- baseline: dynamic annual-average storage cost recovery;
- variant: retained legacy storage tariff.

VALUE creates a new immutable Study from the baseline and preserves the data
pack, years, PSM, investment, expansion caps, planning, transition, parameters
and runtime settings. The changed-dimension contract must refuse a controlled
comparison if any additional scientific identity differs.

The learner creates the Study and launches the Run as two separate actions.

## Comparison and evidence

The guided comparison has exactly three rows:

1. Baseline data + dynamic storage pricing;
2. Windy or High-demand data + dynamic storage pricing;
3. Baseline data + legacy storage tariff.

The summary is calculated by the backend from stored result artifacts. React
does not reconstruct scientific quantities. It includes:

- teaching-window resource/system cost;
- physical operating cost and cost per served MWh;
- operational carbon, overall carbon and total emissions;
- VRE available, accepted and unused energy;
- storage charge, discharge and terminal SOC;
- blackout/load shedding;
- planning admissions, failures and commissioning changes;
- a declaration of the data, module or other dimension that changed.

The detailed route opens the existing period bids, accepted dispatch, SOC,
curtailment attribution, cost ledger, carbon ledger, planning pipeline,
provenance and raw JSON artifacts.

## Build from VALUE 101

After the guided exercises, the learner may copy a teaching Study into the
ordinary Study composer. This is the bridge to a research model, not a second
editor. The user can select an installed data pack, years, compatible modules,
parameters and runtime settings.

The composer presents scientific meaning before implementation identifiers.
Incompatible choices remain visible but disabled. The reason names the missing
data role, capability or contract and suggests a specific corrective action.
VALUE never silently replaces a scientific choice.

A user with British data can build a GB VALUE Study by mapping that data to the
same 25 semantic roles, validating units and chronology, packaging provenance
and hashes, copying the teaching Study, selecting the new pack, restoring
production planning assumptions and choosing annual or pathway execution. An
arbitrary CSV is not a valid pack until the adapter and validation contracts
pass.

The John pilot does not distribute or install a real UK data pack.

## Three-zone network-constraint exercise

The optional exercise is separate from the minimum VALUE 101 run. It uses one
complete synthetic network pack with North, Central and South zones, two fixed
lossless corridors and at least one hand-explainable congested period.

The market path is the already approved staged design:

1. national bid-at-cost ahead market;
2. simultaneous zonal balancing and fixed-network redispatch;
3. final physical dispatch and storage SOC enter the result and next state.

This is a zonal transport/redispatch representation. The user-facing name is
**Network constraints & redispatch**. Documentation must not call corridor
transfers AC power flow, DC load flow, N-1 security analysis or physical line
flows. The product may group it under linear/DC network constraints, but the
method statement must retain the transport-model boundary.

The exercise compares matched copperplate and constrained runs using identical
national demand, initial fleet, weather, bids and ahead schedule. Results show:

- corridor transfer, rating and utilisation;
- congestion periods;
- accepted upward and downward redispatch;
- thermal, VRE, storage, interconnector, DSR and VOLL actions;
- network-added and network-avoided curtailment;
- load shedding;
- redispatch resource cost and pay-as-bid settlement;
- final system-cost difference;
- the authoritative redispatch ledger.

No executable transmission-expansion module is included. Corridor capacities
remain fixed and transmission CEM remains an external interface.

## Completion report and reset

The user may export a local `VALUE 101 completion report`. It contains only
local evidence:

- completed course steps;
- Study IDs and immutable revision identities;
- pack and selected-module identities;
- Run IDs and statuses;
- controlled-comparison gate results;
- network exercise status when attempted;
- errors and diagnostic-bundle paths.

Nothing is uploaded and no telemetry service is added.

**Reset VALUE 101** requires explicit confirmation. It removes only VALUE 101
browser progress, teaching-created Studies, teaching Runs and teaching report
state. It does not remove data packs, external modules, ordinary research
Studies or research Runs. The backend identifies teaching records by explicit
origin metadata, never by a name substring.

## Windows pilot

The offline, current-user installer bundles pinned Python 3.10, Node, locked
scientific dependencies, the VALUE application, the three VALUE 101 packs, the
synthetic network pack and English teaching material. It does not require
administrator rights, Git, Python, Node, a terminal or internet access after
download.

The installer must retain transactional replacement, process ownership checks,
diagnostic logs, safe uninstall and application-state isolation already added
to the Castle prototype. The final package opens `http://127.0.0.1:8800/` and
uses the API at `http://127.0.0.1:8766/`.

## Acceptance gates

1. All three teaching packs validate all 25 roles and reproduce deterministic
   hashes from a clean build.
2. Byte/semantic comparison proves Windy changes only wind roles and High demand
   changes only real/forecast demand roles.
3. The baseline uses the production module registry and executes the real
   two-year PSM-CEM lifecycle.
4. The storage variant differs only in `storage_cost`.
5. Tutorial results remain non-annual and cannot enter annual scientific
   comparison claims.
6. The browser journey creates and runs all three Studies without terminal use.
7. Module cards expose both plain-language and technical evidence.
8. Disabled module choices provide a concrete compatibility reason.
9. Matched copperplate and three-zone network runs conserve energy and reconcile
   redispatch, curtailment and cost identities.
10. AC is absent from every ordinary user surface and public release artifact.
11. Completion export and scoped reset do not alter unrelated records.
12. Windows install, repeated install, offline start, stop and uninstall pass.
13. Frontend lint/build/render/E2E, focused Python tests, complete Python suite,
    source-release scan and retained Scheme C hashes pass.
14. A clean-user timed rehearsal completes the core baseline/data/module route
    in no more than 30 minutes.

## Non-goals

- distributing the real UK research or 1000 TWh reproduction pack to John;
- annual or ten-year British execution in the teaching package;
- AC-OPF or public AC feasibility;
- transmission expansion;
- browser-side result calculations;
- cloud hosting, accounts or telemetry;
- arbitrary unvalidated file upload;
- modifying retained Scheme C source or accepted hashes.
