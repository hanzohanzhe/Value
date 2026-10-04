# VALUE-UK Research Suite and Methodology Design

Date: 25 August 2026

Status: proposed for implementation review

## Purpose

VALUE 101 remains a small, isolated Windows teaching product. After installing
it, a modeller must be able to install one separately distributed UK research
asset and obtain two ordinary ten-year Studies:

1. a national single-node, or copperplate, VALUE-UK Study; and
2. a fixed-zonal-network VALUE-UK Study with congestion and redispatch.

Both Studies use the same installed application, module registry, annual
PSM-CEM lifecycle and result surfaces as VALUE 101. They differ in declared
data and system domain. Neither Study starts automatically when the data asset
is installed.

This work prioritises an executable research workflow. Scientific-baseline
promotion, independent validation and publication claims remain later gates.
The zonal Study is therefore executable but labelled as an experimental
post-thesis extension until those gates have been completed.

## Product boundaries

The Windows product is split into two deliverables.

### VALUE 101 application installer

`VALUE-101-Setup.exe` contains:

- the local VALUE website and Python runtime;
- the production VALUE module registry;
- the deterministic CC0 VALUE 101 teaching data;
- the teaching single-node and fixed three-zone examples;
- generic data, module and extension installation workflows.

It does not contain the UK research observations, the doctoral 1000 TWh data
or the GB research network pack. Reinstalling it must preserve independently
installed research packs and saved Studies unless the user explicitly removes
them through the product lifecycle controls.

The final installer is rebuilt from the completed VALUE source; it is not a
renamed or recopied earlier pilot EXE. It includes the new research-suite
installer, UK Study-template handling, updated readiness and run surfaces, and
the maintained documentation links required by this design.

### VALUE-UK research suite

`VALUE-UK-Research-Suite.bundle.zip` is a non-executable local data asset. Its
outer manifest uses `value.research-suite/v1` and contains two independently
versioned, independently hashed components:

- `value-uk-open-data-pack-v1`, the complete 25-role UK base Data Pack; and
- a VALUE-named GB fixed-zonal Network Pack.

The suite also contains two declarative Study templates and the rights,
attribution, source and transformation records required by both components.
The outer ZIP is a convenience transaction; it does not merge the two pack
identities or let the Network Pack replace the base Data Pack.

No Python, JavaScript, DLL, shell script, executable or dependency is permitted
inside the research suite. Archive traversal, symlinks and undeclared files are
rejected.

## Research-suite manifest

The outer manifest records:

- suite ID and version;
- schema version `value.research-suite/v1`;
- base Data Pack member, ID, manifest SHA-256 and bundle SHA-256;
- Network Pack member, ID, manifest SHA-256 and bundle SHA-256;
- Study-template member and SHA-256;
- total compressed and uncompressed bytes;
- suite-level attribution and rights files;
- a statement that component rights remain object-specific;
- compatibility requirements for VALUE application, data contract, network
  contract, modules and model clock.

The Study-template member is JSON data, not executable code. It may reference
only component IDs declared by the same suite and built-in VALUE module IDs
available in the installed application.

## Installation transaction

The Data page adds one generic action, **Install a research suite**, alongside
the existing single Data Pack installer. The user selects the suite ZIP and
acknowledges its source and rights records.

VALUE then:

1. streams the upload to local staging;
2. validates the outer schema, safe member names and file inventory;
3. verifies every outer and component SHA-256;
4. checks free space for both packs, staging and rollback headroom;
5. validates the 25-role base pack with the existing Data Pack validator;
6. validates the Network Pack topology, zones, cutsets, ratings, demand
   allocation, spatial mapping and clock with the existing network validator;
7. resolves every module and extension referenced by the Study templates;
8. checks that the two templates use only their declared component identities;
9. promotes the two packs into the VALUE data home;
10. creates immutable local revisions of the two Studies; and
11. writes one installation record containing all component identities and
    hashes.

Promotion is all-or-nothing. A failure before promotion leaves no installed
component. A failure after the first rename rolls back both component targets
and does not create either Study. Reinstalling identical bytes is idempotent.
An existing ID with different bytes is a collision and requires a new
versioned pack ID; VALUE never overwrites it.

Original data under the legacy local FORCE data home are read only when the
suite is assembled. They are not moved, renamed or deleted. The distributed
suite and installed runtime identities use VALUE names.

## Installed Study templates

Installation creates saved, unrun Study revisions. They appear in the ordinary
Studies and Runs interfaces and can be cloned or revised like any other Study.

### VALUE-UK copperplate 2025-2034

The Study declares:

- years 2025 through 2034;
- the installed 25-role UK base Data Pack;
- the national single-node system domain;
- interconnectors as external boundary offers in the base pack;
- the built-in bid-at-cost PSM and selected built-in annual CEM chain;
- the built-in dynamic annual-average storage-cost recovery method;
- 17,520 half-hour periods in every complete model year;
- full annual compact result evidence and no internal network data.

Check readiness validates and freezes the Data Pack, exact modules,
parameters, clock, resource estimate and input snapshot. It never searches for
or displays a fictitious Network Pack.

### VALUE-UK fixed-zonal network 2025-2034

The Study preserves the same years, national-demand scenario, base Data Pack,
PSM-CEM modules and exposed policy assumptions, then adds:

- the fixed-zonal system domain;
- the built-in zonal redispatch/balancing implementation;
- the installed GB Network Pack;
- `scenario_scaled_zonal_shares`, so national demand remains controlled by the
  base research pack and the Network Pack allocates that total to zones;
- fixed, time-dependent signed boundary capabilities;
- zonal mapping and network/redispatch result evidence.

Check readiness must resolve and freeze the exact Network Pack ID and hash. A
missing zone, cutset, rating, allocation, spatial mapping or period is a hard
error. The run never silently chooses another Network Pack and never falls
back to copperplate.

The fixed-zonal Study is labelled **Experimental post-thesis network method**.
This label describes scientific maturity; it does not disable execution.

The two installed templates therefore differ only in their declared system
domain, balancing implementation and Network Pack. Their base data, national
demand, annual clock, storage-cost method and CEM chain are identical. A user
may clone either immutable revision and select the legacy storage tariff or a
compatible external module in Advanced mode; that clone is a new Study and
does not alter the comparison templates.

## Run behaviour

Both templates expose **Run complete Study**. A ten-year launch requires a
successful readiness check and an explicit confirmation showing period count,
estimated disk, memory and runtime. Closing the browser does not stop the local
worker. Cancellation uses the existing safe-boundary mechanism, and annual
checkpoints remain local and portable.

The annual lifecycle is unchanged:

1. advance the existing planning pipeline;
2. clear every half-hour through the selected PSM;
3. complete the selected balancing or redispatch stage;
4. assemble annual physical, cost, carbon, storage and curtailment evidence;
5. calculate VRE and storage expansion headroom;
6. evaluate owner-level investment;
7. admit, delay or reject planning projects;
8. commission and retire assets; and
9. construct the next model-year state.

For the zonal Study, the actual post-redispatch charge, discharge and dispatch
update the physical annual state. Network congestion does not add a
transmission-expansion decision to the CEM. The transmission-expansion
interface remains unselected and non-executable in this release.

## User interface

The Data page reports four separate states:

- suite not installed;
- validating and staging;
- base and Network Pack installed, Studies created;
- failed, with the exact component, role and corrective action.

On success it shows the suite hash, both pack IDs and hashes, installed bytes,
rights files and the two created Study revisions. Buttons open the copperplate
or zonal Study; neither button launches a Run.

The Studies composer describes the system-domain choice in physical terms:

- **National single node** — one GB market node with no internal transmission
  constraints;
- **Fixed GB zones and redispatch** — national ahead-market clearing followed
  by fixed-boundary zonal redispatch.

The Runs page states the topology, base Data Pack and Network Pack, if any,
before launch. Zonal results link to **Network & redispatch**. Copperplate
results do not show empty network panels.

## Methodology deliverables

The release adds one maintained English source and one generated PDF:

- `docs/methodology/VALUE_METHODOLOGY.md`;
- `VALUE-Methodology.pdf`.

The PDF is generated from the maintained source and is shipped beside the two
existing manuals. It is not manually edited. The final John/pilot folder
therefore contains:

1. `VALUE-101-Setup.exe`;
2. `VALUE-UK-Research-Suite.bundle.zip` as a separate data download, not
   embedded in the EXE;
3. `START-HERE-VALUE-101-Guide.pdf`;
4. `START-HERE-VALUE-101-TO-VALUE-UK-Guide.pdf`;
5. `VALUE-Methodology.pdf`; and
6. SHA-256 records for the installer and research suite.

The methodology explains the executable model rather than advertising it. It
contains:

1. scope, model clock, information structure and notation;
2. Data Pack, Study, Module, Run and evidence identities;
3. national bid-at-cost PSM, offers, dispatch and settlement records;
4. thermal generation, VRE, imports, demand and load shedding;
5. storage SOC, efficiency, power and energy constraints;
6. dynamic annual-average storage cost recovery and legacy tariff;
7. VRE and storage expansion caps;
8. owner-level investment logic;
9. planning pipeline, admission, completion, failure and commissioning;
10. retirement and annual state transition;
11. system-cost, policy-cost and carbon ledgers;
12. hydrology and other optional-domain boundaries;
13. fixed-zonal transmission constraints and redispatch;
14. result artifacts, reproducibility and declared limitations.

Every module section states its purpose, lifecycle position, required inputs,
units, state reads and writes, governing equations or algorithm, outputs,
configurable parameters, numerical or behavioural assumptions, and known
limitations. Statements are checked against the active VALUE implementation
and retained thesis/reproduction evidence. A method that is not in the thesis
is not attributed to the thesis.

### Transmission methodology

The transmission chapter is explicitly labelled as a post-thesis VALUE
extension. It documents:

- DSO-aligned computational zones and immutable asset-zone assignment;
- treatment of unresolved English assets through the declared representative
  England connection and offshore assets through the nearest-coast rule;
- ETYS-derived fixed, signed, direction-specific cutset capabilities and
  optional time-dependent maintenance ratings;
- the lossless transport representation used by this version;
- national bid-at-cost ahead-market clearing followed by zonal redispatch;
- redispatch participation by thermal units, VRE curtailment, storage,
  interconnector boundary offers, zero-capacity DSR interfaces and VOLL-priced
  load shedding;
- pay-as-bid redispatch records and separate physical, cash-flow, policy and
  system-resource-cost ledgers;
- post-redispatch storage-state updates using actual charge and discharge;
- separation of forecast-driven balancing from congestion-driven redispatch;
- gross potential curtailment, final physical curtailment and redispatch impact;
- demand authority under `scenario_scaled_zonal_shares` and the independent
  `network_pack_absolute_demand` alternative;
- expected unserved-energy and expected-interruption-hours reporting;
- interconnectors as external boundary offers rather than internal GB lines;
- no AC power flow, reactive power, voltage, transient stability, N-1 security,
  endogenous losses or transmission expansion claim.

The chapter explains that the model is a zonal transport and redispatch model,
not a network security assessment. It also explains that changing the bidding
strategy can change redispatch behaviour because redispatch follows declared
offers rather than an undocumented physical priority order.

## Verification for this construction phase

This phase verifies executability and packaging, not a new scientific
baseline. Verification is deliberately layered:

1. validate the outer suite and both component manifests and hashes;
2. install into an empty isolated VALUE data home;
3. prove both Study revisions are created but no Run starts;
4. run readiness for both ten-year templates;
5. run a bounded copperplate production-path smoke;
6. run a bounded zonal production-path smoke and confirm actual network and
   redispatch artifacts;
7. confirm a missing or corrupted Network Pack blocks zonal execution without
   copperplate fallback;
8. rebuild the Windows installer once after source checks pass;
9. install on a clean local pilot state and repeat suite installation and the
   two bounded Runs;
10. regenerate and text-check all three PDFs.

Completion of an actual 350,400-period ten-year Run is not a prerequisite for
building this executable workflow. Until separate long-run evidence exists,
the UI and documentation must say that the templates are configured for ten
years, not that their ten-year scientific results have already been validated.

## Non-goals

This change does not:

- modify the preserved doctoral Scheme C source;
- place rights-governed UK data inside the application installer or source
  repository;
- introduce automatic Internet downloads or require cloud hosting;
- add AC power flow, security analysis or transmission CEM;
- change PSM, CEM, storage, investment or planning science merely to make a
  test pass;
- merge the base and network data identities;
- delete or rewrite old local FORCE data;
- claim that a successful readiness check is scientific validation.

## Acceptance criteria

The design is complete when:

- one non-executable research-suite ZIP installs the two independent packs
  atomically;
- exact component IDs and hashes remain visible and frozen in Run evidence;
- the two immutable 2025-2034 Study templates are created without launching;
- copperplate readiness never asks for a Network Pack;
- zonal readiness resolves the exact compatible Network Pack and fails closed;
- bounded Runs execute the real copperplate and zonal PSM-CEM paths;
- the zonal Run writes congestion, redispatch, curtailment and network evidence;
- the existing VALUE 101 teaching workflow remains operational and isolated;
- installer reinstallation preserves independently installed research data and
  Studies;
- the two manuals and the new Methodology PDF match the shipped application;
- active product files use VALUE identity; and
- retained Scheme C files and hashes are unchanged.
