# Prompt 81 — Extension-bundle lifecycle UI

Execute after Prompt 80. Reuse Prompt 58 module-bundle installation and Prompt
65 extension-bundle validation/transaction code. Act as a software supply-chain
engineer and frontend product engineer. Do not merge module and extension bundle
formats or install third-party dependencies from the browser.

## Objective

Give a normal user a truthful browser workflow for installing, enabling,
upgrading, disabling and inspecting a `force.extension-bundle/v1` package.
Module bundles continue to replace an existing slot; extension bundles may add
capabilities, conditional data roles, parameters, state, artifacts and hooks.

## Work

1. Add a distinct **Extensions** section beside Modules. Explain the three
   extension levels: data-only, replacement module and new model domain.
2. Stream a bounded ZIP to local staging and reuse the Prompt 65 validator for
   inventory, hashes, path safety, manifest, namespace, semantic version,
   licence, FORCE/contract compatibility, capabilities, roles, parameters,
   hooks and member allowlist.
3. Require explicit trust acknowledgement for executable Python. Do not run
   `pip`, accept native binaries, access the network or claim OS sandboxing.
4. Show dependencies, composed modules, maturity and any missing runtime/data
   requirements before installation. Installation remains atomic and rollback
   safe.
5. Prevent namespace/ID/version collisions, same-version byte changes,
   incompatible downgrades and disabling/uninstalling an extension referenced by
   saved Studies, checkpoints, active runs or retained history.
6. After a successful lifecycle change, refresh the same workspace registry used
   by Studies and Data. Never maintain a browser-only installed list.
7. Provide source hash, installation path boundary, licence, manifest download,
   conformance status and dependent Study list. Structural conformance must not
   be labelled scientific validation.

## Tests and acceptance

Use the Prompt 65 toy extension plus hydrology/network fixtures. Cover valid
install, idempotent reinstall, upgrade with declared state migration, dependency
failure, collision, ZIP traversal, decompression excess, unlisted executable,
bad hash, missing licence, disabled dependency and in-use removal. Browser E2E
must install an extension, make its conditional role appear, create a Study,
then prove removal is blocked.

Retained built-ins cannot be overwritten. Existing Prompt 58 module installation
tests must remain unchanged and passing.

