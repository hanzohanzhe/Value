# VALUE 101 annual teaching and VALUE identity redesign

Date: 25 August 2026

Status: proposed for final review

Supersedes: `2026-08-24-value-101-teaching-redesign.md` where this document
changes the run clock, annual-economics boundary, teaching route, public domain
model and product identity.

## Purpose

VALUE 101 must teach a new modeller two different things without confusing
them:

1. how a half-hourly power-system market clears; and
2. how a complete annual PSM-CEM model produces revenue, investment, planning,
   capacity and curtailment outcomes.

The first lesson therefore runs one day through the real VALUE PSM only. The
second run executes two complete model years, each containing 17,520 half-hour
periods, through the real annual VALUE PSM-CEM lifecycle. A one-day result must
never be used to decide annual revenue, investment or expansion.

This redesign also removes the obsolete FORCE and Scheme C product identity,
corrects the Study composer's system/optional-domain semantics, and replaces
the toy-like customisation lesson with real data-pack, module and extension
workflows.

## Product and identifier identity

The application, installer and model are VALUE. This development baseline has
no user-owned historical Studies, Runs, hashes or external module packages that
need a compatibility migration. The migration is therefore clean rather than
dual-named.

All active product identifiers must use VALUE terminology, including:

- user-facing names, labels, help text, errors and status messages;
- runtime-capability names and requirement-lock filenames;
- module and extension IDs;
- manifest fields and contract/schema namespaces currently prefixed `force`;
- active Python class names and active implementation directories containing
  `scheme_c` or `scheme-c`;
- API payload values, acknowledgement values and generated JSON evidence;
- installer, launcher, diagnostic and build-script names;
- frontend source, tests, examples and generated documentation.

The active built-in modules use clear VALUE identities, for example:

- `value-bid-at-cost-psm`;
- `value-dynamic-storage-cost`;
- `value-legacy-storage-tariff`;
- `value-agent-investment`;
- `value-planning-pipeline`;
- `value-vre-expansion-policy`;
- `value-storage-expansion-policy`;
- `value-annual-state-transition`;
- `value-zonal-redispatch`.

There is no runtime alias from an old FORCE or Scheme C identifier. A clean
installation contains no old teaching state. The separately preserved doctoral
reproduction model remains outside this VALUE product migration and is not
modified by this work.

Historical engineering reports may be retained outside the installable source
and runtime products when they are needed as audit records, but no released
installer, generated manual, active manifest, API response or ordinary product
screen may expose the old identity. Release scans fail on an active-product
case-insensitive match for `FORCE`, `force-`, `scheme-c` or `scheme_c`.

## Teaching data

VALUE 101 uses deterministic CC0 synthetic data. It does not distribute the UK
research or 1000 TWh reproduction data.

The baseline teaching pack contains complete 2025 and 2026 chronologies:

- 17,520 half-hour periods in 2025;
- 17,520 half-hour periods in 2026;
- 35,040 periods in total;
- continuous demand, forecast demand, solar, onshore wind, offshore wind,
  import price and import availability inputs;
- a complete fleet, cost, policy and planning input set bound to the canonical
  25 VALUE data roles.

The annual synthetic series must be deterministic and must include enough
variation to exercise thermal generation, imports, storage charging and
discharging, renewable acceptance, renewable curtailment and at least one
planning/investment pathway. Data-generation metadata records the seed,
algorithm version, units, chronology and SHA-256 values.

The one-day lesson reads one declared, contiguous 48-period slice from this
same annual baseline pack. The chosen date and period indices are visible in
the Study and Run evidence. The full two-year run reads all 35,040 periods.
This keeps the physical inputs comparable while changing only the declared run
scope.

The installer bundles one baseline teaching pack and, when the optional network
lesson is retained, one matched network pack. It does not bundle Windy,
High-demand or another preconfigured data variant. Selecting a prepared variant
does not teach a researcher how to adapt, validate and install their own data.

The data are synthetic. Full chronology makes annual revenue, cost, investment,
planning and curtailment internally meaningful for this synthetic system; it
does not turn the result into British evidence.

## Two run modes

### Run one day: PSM lesson

The primary quick action is named **Run one-day market lesson**.

It executes exactly 48 half-hour periods from one declared model year through
the selected production VALUE PSM. It records:

- submitted bids and offers;
- accepted dispatch and clearing results;
- storage charging, discharge and SOC;
- available, accepted and curtailed VRE;
- imports, unmet demand and energy-balance evidence;
- module, data, parameter and period provenance.

It does not invoke investment, expansion caps, project admission or annual
state transition. The result page does not show annual revenue, annual system
cost, annual carbon, annual investment or capacity expansion. Its banner says
**One-day PSM lesson — 48 half-hours, no CEM or annual economics**.

### Run complete two-year model

The second action is named **Run complete two-year model**.

It requires a Study covering exactly 2025 and 2026 and executes 17,520 periods
per year. The annual lifecycle is:

1. advance the existing planning pipeline for the current year;
2. clear all 17,520 PSM periods;
3. calculate annual market, cost, carbon, storage and curtailment evidence;
4. evaluate VRE and storage expansion headroom;
5. run owner-level investment decisions using annual evidence;
6. admit, delay or reject planning projects;
7. construct the next model-year state;
8. repeat the complete process for 2026.

The result is eligible for annual synthetic-system economics and for the
two-year synthetic capacity pathway. It is not eligible for a UK national
claim. The UI shows the expected runtime and disk estimate before launch,
supports cancellation at safe boundaries, and continues in the background if
the browser closes.

## VALUE 101 information architecture

The Learn page has two clearly separated sections.

### Guided model lesson

1. Read the five building blocks: Data, Module, Study, Run and Results.
2. Inspect the baseline data roles and selected VALUE module chain.
3. Save the baseline Study.
4. Run the one-day PSM lesson and inspect bids, dispatch, SOC and curtailment.
5. Launch the complete two-year model when annual results are required.
6. Inspect annual revenue, cost, carbon, investment, planning and capacity
   change from stored result artifacts.
7. Continue to the real data, module or domain development route when the user
   wants to change the model.

Creating a Study, launching the one-day Run and launching the full two-year Run
are three explicit actions. A saved but unrun Study is labelled **Saved — not
run**. Saved Studies and executed Runs are not presented as one list.

The Learn page contains no preconfigured Windy, High-demand or storage-tariff
experiment and no completion gate that requires several preset Studies. An
installed alternative module may remain available in the ordinary research
module catalogue, but selecting it from a toy tutorial is not a learning goal.

### Build a research model

The second section is not a preloaded click demonstration. It presents three
real development routes and opens the corresponding working surface:

1. **Bring your own data**;
2. **Build or replace a module**;
3. **Add a model domain**.

Every route shows what the user must supply, the exact package format, the
contract and validation steps, and the point at which the new component becomes
selectable in a Study.

## System domain and optional domains

### System domain

The system domain defines the physical dispatch problem that every selected
PSM period must satisfy. Basic mode shows only executable, user-meaningful
choices:

1. **National single node** — no internal transmission constraint;
   interconnectors remain boundary offers.
2. **Fixed zonal network and redispatch** — the reviewed fixed-corridor method,
   shown only when its complete signed network pack and executable balancing
   module are installed.

AC feasibility is not offered. A contract-only network component is not a
system-domain choice. The unimplemented transmission-expansion interface is not
presented as executable functionality.

### Optional domains

An optional domain adds a scientifically distinct state, input or result family
to the selected system domain. Basic mode lists only installed, executable
domains with satisfiable data requirements. Hydrology may appear when its
run-of-river or reservoir implementation and required data roles are available.

The following are developer components, not optional scientific domains, and
must not appear in Basic mode:

- raw network data contracts;
- solver-neutral interface contracts;
- audit/test extensions;
- lifecycle interfaces without an executable implementation;
- toy fixtures.

Advanced mode may expose technical dependencies, versions, contract names,
missing roles and maturity. It must still describe their scientific meaning
before identifiers.

## Real data workflow

The Data page provides an actual route rather than explanatory cards only:

1. view and download the canonical 25-role VALUE data-pack template;
2. inspect required fields, formats, units, time semantics and validation rules
   for each role;
3. download an adapter example;
4. upload or select a completed data-pack bundle;
5. validate schema, chronology, units, checksums, licence and provenance;
6. receive row-, field- and role-specific errors;
7. install the validated pack into the local registry;
8. select it in an ordinary Study.

The Data page does not offer a prepared scientific variant as a substitute for
this workflow. The first successful custom-data exercise ends only when the
user's own validated pack is installed and selectable in an ordinary Study.

## Real module workflow

The Modules page separates using an installed module from developing one. A
researcher can:

1. select the slot to replace;
2. read its input/output contract and capability requirements;
3. download a slot-specific starter bundle containing a manifest, entry point,
   minimal implementation and focused tests;
4. implement the scientific method without changing the orchestrator;
5. run the declared contract/conformance tests;
6. package the module bundle;
7. install it locally with explicit trust acknowledgement;
8. see compatibility or exact corrective errors;
9. select the compatible module in Advanced Study composition.

Changing bidding, storage pricing, investment, planning or expansion policy is
a module replacement. Adding transmission, hydrology or another new state and
result family is an extension/domain change, not a fake module-slot selection.
The Learn page does not offer a one-click legacy-tariff clone. A retained
reproduction module, if installed, appears only in the ordinary module catalogue
with its method and scope.

## Real domain-extension workflow

The Add domain route supplies an extension starter bundle and explains:

- new semantic data roles;
- typed contracts and declared capabilities;
- lifecycle hooks and execution ownership;
- state carried between model years;
- result artifacts and ledger integration;
- compatibility, conservation and failure tests;
- installation and Study activation.

An extension that only declares a contract but has no executable module is
listed in developer documentation, not as a runnable Basic-mode option.

## Results and scientific labels

The one-day page prioritises period evidence: bids, dispatch, price, storage,
VRE availability and curtailment. It never annualises the 48 periods.

The full two-year page shows:

- annual resource/system cost and physical operating cost;
- generator and storage revenue/cost evidence;
- operational and embodied carbon ledgers;
- VRE available, used and curtailed energy;
- storage charge, discharge and terminal SOC;
- investment proposals and accepted capacity;
- planning stage, location, delay, failure and commissioning;
- opening and closing fleet by technology;
- complete provenance and machine-readable artifacts.

The browser reads stored artifacts and does not reconstruct scientific totals.
Every result states **Synthetic annual VALUE 101 system — not a UK result**.

## Documentation and PDF

The installer contains one English PDF named `VALUE-101-Guide.pdf`, generated
from the same reviewed source as the in-app lesson. It uses the final UI labels
and contains:

- installation, start, stop and uninstall instructions;
- exact one-day and complete-two-year run steps;
- the 48 versus 17,520-period distinction;
- the annual lifecycle in correct execution order;
- definitions of system and optional domains;
- the real data, module and domain development routes;
- result interpretation and synthetic-evidence limits;
- troubleshooting and local file locations.

The PDF does not describe derived run-policy fields as editable Study fields,
does not reference a nonexistent documentation path, and does not expose the
obsolete product identity. UI labels, in-app text, Markdown and PDF are checked
from one source-of-truth vocabulary.

## Windows installer

The final offline Windows package remains current-user, no-admin and
terminal-free. It bundles the VALUE application, pinned runtimes and
dependencies, the complete annual synthetic teaching packs, the PDF and the
real starter templates required by the research routes.

The installer retains transactional replacement, progress reporting, process
ownership checks, isolated local state, safe stop and safe uninstall. The final
build is produced only after source, data, documentation and focused tests pass.
Installer build and final install verification are not repeated after every
code change.

## Acceptance gates

1. A repository and release scan finds no obsolete identity in active product
   identifiers, runtime payload, UI, API examples, generated documents or
   installer content.
2. The clean installer creates no obsolete-named directory, service, shortcut,
   process label or state field.
3. The annual baseline pack contains exactly 17,520 ordered half-hours for each
   of 2025 and 2026 and validates all 25 roles.
4. The one-day Run executes exactly 48 contiguous periods through the real
   VALUE PSM and invokes no CEM stage.
5. One-day result surfaces contain no annualised economic or expansion claim.
6. The full two-year Run executes exactly 35,040 PSM periods and the complete
   annual PSM-CEM lifecycle twice.
7. Full-year revenue, cost, carbon, curtailment, investment, planning and
   capacity ledgers reconcile from stored artifacts.
8. The 2026 opening state contains commissioned and model-invested assets from
   the 2025 transition where the synthetic fixture produces them.
9. Basic Study composition shows only the national single-node and executable
   fixed-zonal system domains.
10. Basic Optional domains contain no contract-only, toy, audit or unimplemented
    expansion item.
11. Data, module and domain routes download or open real templates, validate
    real bundles and lead to installed/selectable components.
12. The runtime payload and Learn page contain no Windy, High-demand or
    fixed-tariff preset experiment and no three-Run completion requirement.
13. Saved Studies and Runs remain visibly distinct; an unrun Study cannot look
    completed.
14. Frontend lint/build/render and focused Python contract tests pass.
15. Before packaging, one complete two-year annual Run finishes and passes
    energy, storage, cost, carbon, investment, planning and transition audits.
16. The final EXE passes clean install, running reinstall, stop, restart,
    one-day baseline and one complete two-year Run without altering the separate
    main-model workspace.
17. The English PDF text and screenshots match the final installed build.
18. The final EXE and PDF receive SHA-256 hashes and are frozen together in one
    John pilot directory.

## Non-goals

- distributing UK research or doctoral reproduction data;
- claiming synthetic annual results are British results;
- AC power flow, AC OPF or N-1 security analysis;
- implementing transmission expansion;
- using a one-day clock for annual investment or expansion;
- precomputing tutorial answers;
- adding cloud hosting, accounts or telemetry;
- preserving obsolete pilot state or obsolete product identifiers.
