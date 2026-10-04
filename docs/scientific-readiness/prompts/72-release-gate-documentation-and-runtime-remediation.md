# Prompt 72 — Release-gate documentation and runtime remediation

Execute only after the first Prompt 71 gate. This is a bounded release-engineering
remediation; it must not alter PSM/CEM equations, accepted scientific fixtures or
the preserved Prompt 64/Scheme C baselines.

## Evidence that opened this prompt

The first complete Python 3.10 gate produced 292 passes, 22 expected skips, 67
passing subtests and five failures:

1. generated module and parameter tables were stale after Prompts 68-70;
2. the mathematical reference still described network/hydrology as wholly
   unsupported and did not name the new manifests;
3. the isolated test environment installed open-core/solver/validation extras but
   omitted the locked `force-native` data/runtime extra, so two preflight tests
   and one capability-isolation test correctly reported missing xarray, netCDF4
   and pyproj.

## Work

1. Install the locked `force-native` extra into the independent Prompt 65-71
   environment. Do not modify the original FORCE environment.
2. Regenerate `docs/generated/PARAMETERS.md` and `docs/generated/MODULES.md` from
   executable manifests and parameter schemas.
3. Amend `docs/MATHEMATICAL_REFERENCE.md` to name and bound the hydrology, DC,
   experimental AC-feasibility and experimental transmission-expansion
   capabilities. Keep AC OPF and long-horizon endogenous network claims explicitly
   unsupported.
4. Teach runtime capability reporting that selected SciPy-backed DC/AC modules
   require the solver extra. Do not broaden supported Python versions.
5. Re-run the exact Prompt 71 Python suite, retained-source hashes, frontend
   lint/build/tests, clean-package install and archive scan. Record both the first
   failed gate and the post-remediation gate.

## Acceptance

- all five original failures pass for their stated reason;
- no scientific output or Prompt 64 frozen graph changes;
- generated-document `--check` passes;
- missing optional dependencies remain fail-closed;
- the final Prompt 71 decision remains capability-specific.
