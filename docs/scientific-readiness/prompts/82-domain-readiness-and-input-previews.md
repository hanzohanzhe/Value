# Prompt 82 — Domain readiness and input previews

Execute after Prompt 81. Read the canonical network/hydrology adapters,
preflight, Prompt 67–70 failure fixtures and current Run readiness card. Act as a
power-system data reviewer and scientific UX engineer. Do not solve or alter a
Study in the browser.

## Objective

Before launch, explain what physical system the selected Study will actually
run and why it is or is not ready. Build previews from bounded backend summaries
of validated canonical inputs.

## Required previews

### Network

Show bus/branch/transformer counts, islands, one reference/slack per island,
voltage levels, in-service capacity, generator/storage/import/demand mapping,
nodal-demand reconciliation and optional dynamic-rating/contingency coverage.
Use a compact topology schematic only when it helps identify connectivity; it
must not imply geographic accuracy without declared coordinates.

### AC feasibility

Show the declared active schedule source, generator P/Q coverage, slack identity,
reactive-demand coverage, voltage/branch limits, initial-state availability,
solver/runtime capability and the exact `local feasibility, not AC OPF` claim.
Do not run AC power flow as a form-field validation request.

### Hydrology

Show run-of-river and conventional-reservoir sites separately, asset/site shares,
inflow chronology coverage, water-to-energy conversion, volume/release bounds,
initial/terminal policy, information structure and missing site/CAPEX evidence.
Keep pumped hydro in storage.

### Transmission expansion

Show existing network stock separately from candidate corridors and model
projects. Summarise endpoints, maximum build, rating/impedance changes, CAPEX,
FOM, lead/economic life, carbon evidence, success/timeline mode and shared
budgets. A zero annual budget must visibly mean proposals are disabled.

## Run readiness

Extend preflight display with grouped errors, warnings and experimental
acknowledgements, each linked to the exact Data, Modules/Extensions or Studies
control that can resolve it. Show estimated periods, artifact volume, solver
runtime and trace impact without presenting an estimate as a result.

## Acceptance

Every preview value must come from the same canonical adapter/preflight object
used at run time and carry definition, unit and source hash. Mutation fixtures
for islands, slack, demand reconciliation, dangling mapping, missing inflow,
reservoir bounds, duplicate candidate and absent economics must produce the
expected blocked state. A valid base single-node Study must not receive network
or hydrology warnings.

