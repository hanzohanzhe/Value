# Prompt 77 — Expanded-frontend truth and interaction-contract audit

Execute first on the separate `0.6.x` expanded-platform line. Before editing,
create a Git rollback commit/tag for the current Prompt 71 candidate and record
the commit, tree and retained Scheme C hashes. Read Prompts 56–58, 61, 65–76,
the workspace endpoint, project save/validation routes, `app/page.tsx`, generated
module/parameter tables and both user guides. Act as a senior frontend
architect, API contract auditor and power-system modeller.

## Objective

Produce one evidence-backed specification for making the already implemented
extension platform usable from the browser. Do not change production behaviour
in this prompt. The output must distinguish:

- capabilities already executable through the ordinary single-node UI;
- capabilities executable in Python/tests but not composable in the UI;
- capabilities that are experimental or not evaluated;
- missing frontend controls, missing API fields and genuinely missing backend
  behaviour.

## Required audit

Trace one draft Study from browser state through POST body, validation, saved
revision, preflight, snapshot, application resolution, checkpoint, result
provenance and reload. Inventory, with exact source locations:

1. base and optional module slots, including `network_expansion`;
2. installed extension manifests, capabilities, requirements, composed modules,
   maturity, parameters, conditional data roles, state and artifacts;
3. which fields exist in `projectForm`, the project API and immutable revision;
4. where `selected_extensions` and `extension_parameters` are lost or ignored;
5. how base and conditional data roles reach pack validation;
6. how the frontend filters `ready`, `experimental` and `not_evaluated` methods;
7. stale single-node-only prose that conflicts with the expanded candidate;
8. which outputs already have query APIs and which are only downloadable
   artifacts.

## Interaction contract

Define, without implementing it yet, an additive versioned browser contract for:

- extension catalogue and installation state;
- capability dependency graph and incompatibility reasons;
- module slots, optional slots and composed-module requirements;
- active conditional data roles for a draft Study;
- extension-owned parameter schemas and effective values;
- maturity/claim status and explicit experimental acknowledgement;
- resolved Study graph preview and graph SHA-256;
- output capabilities for a completed run.

Specify loading, empty, incomplete, incompatible, experimental, solver-missing,
data-missing and failed states. Prefer one server-owned semantic response over
duplicated TypeScript compatibility logic.

## Deliverables

- `docs/frontend/EXPANDED_FRONTEND_CONTRACT.md`;
- a machine-readable gap/field matrix mapping UI → API → model source;
- wireframes for Data, Modules/Extensions, Studies, Run readiness and Results;
- a list of stale or contradictory product statements;
- an execution-impact decision for Prompts 78–84.

## Acceptance and stop conditions

Every proposed field must name its existing source contract or be explicitly
marked new. The audit must prove that no second registry, project schema or
scientific calculator is proposed. Stop if the only way to present a capability
would be to infer it from display names, hard-code module IDs in React, mutate a
saved Study silently or change model equations.

