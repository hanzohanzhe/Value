# Prompt 04 — External module conformance kit

Act as an open-source model SDK maintainer. A third-party module must be selected
and executed through the same path as built-ins.

## Implement

1. Load additional manifests from a workspace module directory without changing
   built-in source.
2. Validate schema, semantic version, slot, contract version, entry point,
   capabilities, parameters, units, determinism and declared artifacts.
3. Add a conformance command that runs a minimal typed fixture for each supported
   slot, including storage-cost policy.
4. Reject duplicate IDs, wrong slots, missing capabilities, undeclared parameters
   and implementations that return the wrong public type.
5. Expose conformance state in the module catalogue. Do not import arbitrary
   uploaded executable code from the browser; local installation remains an
   explicit researcher action.

## Tests and acceptance

- Include one passing external fixture and failures for each contract category.
- A project selecting the fixture reaches production resolution, not a test-only path.
- Existing built-in manifests and retained hashes pass.
