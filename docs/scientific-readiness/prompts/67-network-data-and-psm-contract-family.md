# Prompt 67 — Network data and PSM contract family

Execute after Prompt 65. Read the current v2 single-node PSM contract, declared
clearing-input artifact, independent validation, market replay, data adapters,
cost/carbon ledgers and extension framework. Act as a power-system network model
architect. This prompt defines contracts and adapters only; it does not implement
a DC or AC solver and does not add transmission investment.

## Objective

Create a versioned network-aware PSM contract family that a future module can
implement without editing FORCE core. Preserve the current copper-plate/single-node
PSM as a first-class capability rather than pretending it contains transmission.

## Capability and compatibility boundary

- Keep existing `domain.single_node` Studies and v2 results unchanged.
- Add network capabilities through Prompt 65, including at least
  `domain.network.dc` and `domain.network.ac`; never infer one from the other.
- Reuse one registry, one orchestrator, project revision, snapshot, checkpoint,
  bundle and module provenance. Do not create a network-specific application.
- Interconnectors currently represented as boundary imports remain external
  supply unless explicitly mapped as an internal branch. Do not count them twice.
- Network losses, reactive power, contingencies and transmission expansion are
  optional declared capabilities, not fields filled with misleading zeros.

## Canonical network data roles

Define conditional, versioned roles and adapters for:

- buses/zones with stable ID, voltage level, region and slack/reference eligibility;
- AC lines, DC links and transformers with endpoints, in-service status, thermal
  ratings, reactance/resistance, susceptance, taps/phase shift where applicable;
- generator, storage, import and demand-to-bus mappings;
- nodal/locational demand profiles whose sum reconciles with the base demand role;
- optional contingency sets, dynamic ratings and expansion candidates.

For every field specify units, sign, base quantities/per-unit conversion,
parallel circuits, timestamps, missing values, topology islands, coordinate
system where relevant, provenance and licence. Reject dangling endpoints,
duplicate IDs, invalid impedance/rating, unmapped assets and unexplained demand
mismatch before a run.

## PSM contracts

1. Define a solver-neutral `force.network-psm-input/v1` that references the
   existing economic offers, availability, storage state and interval semantics,
   plus canonical network topology and asset locations.
2. Define typed output capabilities for nodal injection/withdrawal, branch flow,
   congestion, curtailment, blackout, storage, network losses where supported,
   voltage angle, voltage magnitude/reactive power where supported, nodal prices,
   solver/convergence status and residuals.
3. Every unsupported field is absent with a capability/reason, never populated
   with zero. Declare price dual/sign/scarcity conventions by solver module.
4. Extend declared pre-clearing inputs, market artifacts and comparison APIs to
   carry network IDs without breaking existing single-node readers.
5. Define islanding, multiple-slack, infeasibility, load shedding and boundary
   import semantics. The contract must make clear which constraints the selected
   PSM—not the frontend—enforces.
6. Add schema migrations/readers so old single-node bundles remain inspectable.

## Reference adapters and fixtures

Provide deterministic canonical fixtures for:

- one-bus equivalence with the current single-node model;
- two-bus uncongested and congested systems;
- three-bus meshed topology;
- transformer/tap metadata;
- isolated island and invalid topology;
- nodal storage, VRE, thermal and boundary import mappings.

Fixtures define expected conservation and structural invariants but do not claim
solver validation until Prompt 68 or 69 executes them.

## Tests and acceptance

1. Base 25-role packs remain ready for single-node Studies; selecting a network
   capability activates and validates only its additional roles.
2. One-bus canonicalization reconciles exactly with base demand, resources and
   boundary imports and can round-trip through snapshot/export/import.
3. Topology, units, asset mapping, nodal-demand reconciliation and capability
   mismatch tests fail before execution with stable errors.
4. Existing PSM modules cannot be selected for a network Study unless they
   explicitly provide the required network capability.
5. Old v2 Study and run artifacts remain readable and scientifically unchanged.
6. External module conformance can validate contract shape without claiming a
   physically correct power-flow solution.
7. Python, frontend schema/UI, browser and generated-document tests pass. No
   annual or ten-year simulation is required because this prompt adds no solver.

## Stop conditions

Stop if the design requires a second registry/orchestrator, treats external
interconnectors as internal lines without mapping, assumes zero loss/reactive
power while claiming AC, or makes network files mandatory for single-node users.

## Deliverables

- conditional network data schemas/adapters and fixture packs;
- versioned solver-neutral network PSM input/output contracts;
- capability negotiation, preflight, snapshot and artifact integration;
- backward-compatible readers and contract conformance tests;
- bilingual network-module developer guide and Prompt 67 report.
