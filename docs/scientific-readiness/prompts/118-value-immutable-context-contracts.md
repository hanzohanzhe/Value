# Prompt 118 — Immutable VALUE module context contracts

## Purpose

Establish immutable, canonical run and year context contracts for subsequent
runtime wiring without changing the live staged PSM, zonal LP, settlement,
SOC, curtailment, CEM or transition order.

## Delivered boundary

- `RunStaticContext` and `YearContext` recursively freeze JSON-shaped content,
  validate finite numeric values and content identities, and are addressed by
  canonical sorted-key SHA-256 references.
- `ImmutableContextResolver` only returns explicitly bound exact run/year
  hashes and already-resolved module slots. It does not search storage,
  download data or choose a compatible module.
- `ZonalRedispatchDomainV2` carries only run/year references plus a current
  `ZonalRedispatchPeriodSlice`; it contains neither `network_pack` nor an
  annual zonal-demand series. The outer balancing contract remains
  `value.balancing-input/v1`.
- Built-in staged and zonal manifests declare the context lifecycle capability;
  the zonal module additionally declares the v2 redispatch-domain capability.
  Selection rejects a zonal staged pair missing either declared contract.

## Evidence

The specified focused command was run red before implementation and failed
because `gridform_core.module_context` did not exist. After implementation it
ran green with five tests covering canonical references, frozen nested
mappings/sequences, invalid hashes/years/schemas/trace profiles, no annual
arrays in a period slice, duplicate resolver identities/slots, and missing
manifest capabilities.

```powershell
$VALUE_PYTHON = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
& $VALUE_PYTHON -m unittest discover -s tests -p "test_prompt118_value_context_contracts.py" -v
```

The rollback baseline is commit `1375bd9891adcdc9cf5d71b7abd0f18c60da3062`
with tag `value-pre-prompt118-output-context-20260826`.

## Scope retained for later prompts

Prompt 119 alone wires these contracts into the application, orchestrator and
live zonal modules. No static pack loading, annual hand-off, ledger output or
existing market-result payload was altered here.
