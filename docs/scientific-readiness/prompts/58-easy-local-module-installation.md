# Prompt 58: Easy, audited local module installation

Execute after Prompts 04, 12, 31, 34, 50, 56 and 57. Preserve the retained
Scheme C source and the pre-Prompt-58 rollback archive. Read the current
`gridform.module/v2` registry, public module interfaces, conformance runner,
project revision identity, run snapshot contract, source-release boundary and
local loopback server before editing. Act as a power-system software architect,
Python packaging engineer, security engineer and scientific frontend engineer.

## Objective

Let a non-programming FORCE user install a module prepared by a modeller as one
local bundle, inspect its declared scientific identity and conformance result,
enable it, and select it in a Study without editing FORCE or copying files by
hand. Preserve the existing contract-based execution path: the selected Python
implementation, not a frontend label or retained monolithic kernel, must run.

The first release is deliberately a local, self-contained source-bundle
installer. It is not an internet plugin store and must not silently run `pip`,
download dependencies, claim process isolation, or claim scientific validation.

## Non-duplication and architecture boundary

- Reuse `workspace_registry()`, `gridform.module/v2`, public v2 interfaces and
  `module_conformance`. Do not create a second registry or execution path.
- Built-in FORCE manifests and implementations are immutable through this UI.
  An external bundle must use a unique module ID and cannot shadow a built-in or
  another enabled external module.
- Data adapters remain data adapters. Do not mislabel a data pack, demand file
  or mapping as an executable model module.
- A Study stores only registered module IDs. Project revision and run snapshot
  logic must continue to freeze version, contract, entry point, distribution,
  source SHA-256 and resolved graph SHA-256.
- Keep the API loopback-only. Executable module upload must never be exposed by
  the static website server or a non-loopback bind.
- Do not alter retained Scheme C or weaken existing preflight and capability
  compatibility gates.

## Bundle contract

Create `force.module-bundle/v1`, distributed as `.zip`. A bundle contains:

- `force-bundle.json`: schema version, module manifest path, source root and an
  exact SHA-256/byte-size inventory of every other member;
- `force-module.json`: one complete `gridform.module/v2` manifest;
- `src/`: one importable, self-contained Python package containing the declared
  implementation entry point;
- `LICENSE`: required module-code licence;
- `README.md`: optional scientific method, assumptions and citation guidance.

Provide a deterministic command-line builder so a developer can turn a source
folder and manifest into the uploadable ZIP without hand-writing the inventory.

Reject bundles that exceed declared compressed/uncompressed/file-count limits,
contain absolute or parent-traversal paths, duplicate ZIP members, links,
encrypted members, native executables or code outside `src/`; whose inventory
does not match exactly; whose manifest or entry point is invalid; whose module
ID collides; or whose implementation fails conformance. Do not install from a
remote URL. Do not resolve dependencies from the network. Third-party pure
Python code must be vendored under `src/` and covered by its licence.

## Installation lifecycle

Stage under the FORCE data root, validate before promotion, and promote by an
atomic same-volume move into a version-scoped directory. Retain the original
bundle, manifest, inventory, source hash, installation time, conformance report
and installer version. A failed install leaves the previous registry unchanged
and removes its staging directory.

Installed source directories are isolated on disk but run inside the FORCE
Python process. State this truthfully. Activating an installed module may add
only its reviewed version-scoped `src/` path to module resolution. Never append
the general downloads directory or an arbitrary user path to `sys.path`.

Support enable and disable without deleting the retained installation record or
bundle. Disabling must be blocked while a saved Study references the module,
unless a later explicit migration workflow is implemented. Built-in modules
cannot be disabled. Keep already completed run evidence readable.

## Backend and API

Add bounded contracts and loopback endpoints for:

- listing installed bundles and their enabled, conformance and provenance state;
- uploading one bundle with explicit executable-code trust acknowledgement;
- enabling or disabling one installed external module;
- refreshing the single workspace registry after a successful lifecycle action.

Errors must have stable codes and actionable messages. Report structural
conformance separately from scientific validation. Never display a failed or
disabled module as ready/selectable.

## Frontend

Extend the existing **Modules** page, keeping the product UI in English:

1. Add an `Install module` panel with a `.zip` picker, concise bundle contents,
   file-size limit and an unchecked acknowledgement that local Python code will
   execute with the user's FORCE process permissions.
2. Upload only after acknowledgement. Show validation stages and the exact
   failure reason without losing the previously active registry.
3. On success, show module name, ID, slot, version, contract, source hash,
   licence, installation time and conformance status. Explain that conformance
   checks callable shape and a bounded fixture, not scientific validity.
4. Distinguish built-in and locally installed modules on catalogue cards.
5. Provide enable/disable controls for external modules. Explain and block
   disable when saved Studies depend on the module.
6. Refresh Studies immediately after successful installation or enablement.
   Only ready, enabled, slot-compatible modules may appear in selectors.
7. Include a link or copyable command showing how developers build a bundle.
8. Provide keyboard, screen-reader, responsive, empty, uploading, success and
   failure states.

## Tests and acceptance

Use deterministic bundles for at least one CEM policy and one storage-cost or
PSM fixture. Acceptance requires:

1. A valid externally bundled implementation installs, appears in the existing
   registry and Study selector, resolves through the normal module graph and
   executes in a bounded wiring test with explicit execution evidence.
2. Installation does not modify any built-in manifest, implementation or
   retained Scheme C hash.
3. Duplicate IDs, built-in shadowing, wrong contract/slot, missing method,
   missing source entry point and unresolved dependency fail before promotion.
4. ZIP traversal, absolute paths, duplicate members, symlinks, inventory/hash
   mutation, decompression excess and forbidden executable extensions fail.
5. Trust acknowledgement is mandatory and the API remains loopback-only.
6. A failed installation leaves the registry and installed-directory inventory
   byte-for-byte unchanged, apart from an append-only failure log if used.
7. Disable removes the module from new Study selectors without deleting its
   retained package; enable restores it. A referenced module cannot be disabled.
8. Project revisions and run input snapshots record the external implementation
   source hash and version. Historical runs remain readable while disabled.
9. The deterministic builder emits byte-identical ZIPs for identical inputs.
10. Python tests, frontend lint/build, browser interaction tests, source-release
    scan and generated-document checks pass.

## Stop conditions

Stop and report instead of weakening controls if an implementation requires
network dependency installation, native binaries, an incompatible Python
runtime, a built-in ID override, an unversioned arbitrary source path, or a
second execution registry. Do not describe on-disk separation as a security
sandbox. Do not label contract conformance as peer review or scientific proof.

## Deliverables

- `force.module-bundle/v1` contract and deterministic builder;
- transactional local installer and retained installation registry;
- loopback API and English Modules-page installation workflow;
- example developer package and bilingual installation documentation;
- security, rollback, conformance, execution, UI and source-release tests;
- human- and machine-readable Prompt 58 report, including the remaining limits
  of in-process third-party Python execution.
