# Post-Prompt-58 alignment plan

This plan was written after re-reading Prompts 01-58, the release-gap matrix,
Prompt 52 full-run evidence, Prompt 58 module-installer report, the private
GitHub upload report, the current data packs and the 19 August 2026 targeted
data/database audit.

Its purpose is to close only the remaining deltas. It does not reopen accepted
scientific work or make optional network expansion a blocker for the current
single-node beta.

## Global preservation and no-duplication rules

Every prompt below must:

- preserve the retained Scheme C hashes and all historical run bundles;
- reuse the existing v2 orchestrator, one workspace registry, 25-role catalogue,
  canonical adapters, ledgers, run snapshots, module installer and validated
  annual/ten-year evidence;
- create a rollback point before changes and use Git as the version archive;
- never edit the installed `uk-scheme-c-1000twh` pack or rebuild its scientific
  objects merely to change packaging metadata;
- never call conformance scientific validation, or smoke annual economics;
- record a machine-readable change-impact classification before selecting tests.

The test ladder is impact-based:

| Change class | Required evidence |
| --- | --- |
| Documentation, rights metadata or packaging only | targeted tests, source/package scan and clean install; no annual or ten-year rerun |
| UI/API without scientific-path change | unit/E2E, bundle validation and synthetic two-year smoke |
| Data adapter or annual PSM/CEM calculation changes | targeted tests, full 17,520-period year and causal two-year run |
| Storage pricing, investment, pipeline, transition or other multi-year scientific change | preceding gates plus the affected ten-year scenario(s) |
| New network/hydrology contract | analytical fixtures and independent solver checks before any annual claim |

Do not rerun both ten-year storage scenarios unless a frozen scientific input,
PSM/CEM implementation, storage policy or multi-year state transition changed.

## Release-closure line: Prompts 59-64

| Prompt | Only remaining delta closed | Reuses instead of repeating |
| --- | --- | --- |
| 59 | Current working tree, local demo copy and validated private GitHub tree have diverged | Prompt 50 release manifest and the completed private upload |
| 60 | Rights/provenance documents disagree about UK price/policy objects and carbon-database redistribution | Prompts 24, 40, 45 and 55 records and built artifacts |
| 61 | The 803 MiB UK benchmark has no ordinary-user atomic ZIP installation path | Prompt 45 data asset and Prompt 58 transactional ZIP security patterns |
| 62 | The last dependency audit has unresolved high findings, install-script warnings and no final security contact/supply-chain decision | Prompt 25 locks, CI, SBOM and installer |
| 63 | Long-run later-year runtime/memory and annual-only recovery remain beta-quality | Prompts 10 and 22 timing, checkpoint and lifecycle machinery |
| 64 | No current canonical commit has one final clean-clone public-beta decision | Prompts 46, 52 and private GitHub CI; rerun science only when hashes require it |

Prompts 59-62 are public-release blockers. Prompt 63 is a usability/recovery
closure; if it cannot meet its numerical-preservation gate, Prompt 64 may still
release a bounded beta only by retaining and quantifying the limitation.

## Method-three platform-expansion line: Prompts 65-71

These prompts start from the accepted single-node beta. They are a separate
platform release and do not block Prompt 64.

| Prompt | New extension layer | Boundary |
| --- | --- | --- |
| 65 | Versioned extension/capability framework, conditional data roles and module-owned parameter schemas | No network or hydrology equations yet |
| 66 | Typed run-of-river and reservoir hydrology extension | Never duplicate pumped hydro |
| 67 | Network data and PSM contract family | No solver and no transmission investment yet |
| 68 | Reference DC network PSM module | Dispatch only; no endogenous line construction |
| 69 | Optional AC network PSM module | Separate nonlinear capability and solver boundary |
| 70 | Transmission-expansion CEM lifecycle | Adds network assets, proposals, planning and transition explicitly |
| 71 | Cross-version, independent and long-horizon extension release gate | Keeps all v2 single-node Studies reproducible |

## Dependency graph

```text
59 -> 60, 61, 62, 63 -> 64   current public beta

64 -> 65 -> 66
         -> 67 -> 68
               -> 69
               -> 70
66, 68, 69, 70 -> 71         expanded platform release
```

Prompts 60-63 may be developed on separate branches after Prompt 59 establishes
the canonical base, but their accepted changes must be integrated and tested
together by Prompt 64.
