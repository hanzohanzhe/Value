# Prompt 92 Castle 101 release report

Date: 20 August 2026  
Branch: `codex/castle-101-prompt85-92`

## Decision

Castle 101 is ready for a local teaching session and for the Stuart Scott demo.
The bundled lesson now performs the whole intended journey: it opens through
the normal Windows launcher, saves an ordinary Study revision, executes the
selected PSM and CEM chain twice, exposes the market and planning evidence,
compares two storage-pricing configurations, and exports the comparison.

This is a teaching release decision. It is not a new scientific baseline. Each
Castle model year contains 48 half-hour periods. The application labels the run
accordingly and refuses to publish annual cost or carbon differences from it.

| Gate | Decision | What was observed |
| --- | --- | --- |
| Castle data pack | GO | 25 required roles, deterministic hashes and CC0 records pass |
| PSM–CEM execution | GO | Both real 2025–2026 tutorial runs completed |
| Physical and accounting truth | GO | Energy, cost and carbon checks reconcile |
| Learner route | GO | Load, save, run, inspect, clone, rerun, compare and export work in the browser |
| Storage comparison | GO, identity only | Only `module.storage_cost` changes; annual deltas are withheld |
| Documentation and PDF | GO | English, Chinese, quick card, presenter runbook and six-page PDF pass |
| Offline local demo | GO | The route uses loopback only and requires no external request |
| Thirty-minute target | GO for automated dry run | 19.694 seconds of mechanical execution; human reading time remains unmeasured |
| Annual or national claim | NO-GO | Explicitly outside the Castle clock and data scope |

## What runs

Castle is not a mock page. `force-castle-101-v1` supplies a small synthetic
single-node system, and the saved Study resolves these executable modules:

- `scheme-c-psm`;
- `dynamic-annual-storage-cost` or `scheme-c-legacy-storage-tariff`;
- `agent-investment`;
- `planning-pipeline`;
- `vre-expansion-cap`;
- `storage-expansion-scheme-c`;
- `scheme-c-state-transition`.

The baseline run was
`castle-101-base-20260820-084614-cfbe4e99`. The controlled variant was
`castle-101-base-20260820-084620-36df415e`. Both completed two model years on
CPython 3.10.11. Their immutable input snapshots and selected module manifests
are stored with the local runs.

## Live evidence

Both runs wrote 96 period summaries, 96 storage-state rows, 192 declared
clearing inputs and 192 clearing outcomes. The baseline recorded 4,226 orders;
the legacy-tariff variant recorded 4,252. Their maximum absolute energy-balance
residual was `3.552713678800501e-15 MWh`.

The annual cost ledgers are marked `reconciled` for 2025 and 2026. The largest
cost reconciliation residual was `9.313225746154785e-10 GBP`; both carbon
ledgers have zero mass residual. These numbers are diagnostic checks over the
short teaching clock. They are not annual estimates.

The planning index also shows the CEM hand-off rather than a static dispatch
example. No project commissions in 2025. In 2026, one synthetic solar project
commissions with 15 MW. The event is read from the planning artifact used by the
Inspect view.

## Storage-policy comparison

The comparison service reports one changed dimension:

```text
module.storage_cost
dynamic-annual-storage-cost -> scheme-c-legacy-storage-tariff
```

All other declared model dimensions remain controlled. The response is marked
`teaching_diagnostic`, with `annual_metrics_withheld=true`,
`metric_deltas_allowed=false` and `causal_claim_allowed=false`. The export keeps
run and module identities but carries no annual metric rows. This lets the
lesson demonstrate how to design an experiment without pretending that 48
periods provide a policy result.

## Defects found during the gate

The first final-browser attempt exposed a Windows-specific failure. The cloned
Study had a long project ID; appending the timestamp, nonce, staging directory,
data role and filename exceeded the traditional Windows path budget. Windows
reported the last CSV as missing even though the Castle pack was intact. Run
IDs are now capped at 40 characters with an eight-character nonce, and the
atomic staging directory has a shorter name. The same long-name journey now
passes in the real browser.

The gate also closed two test and product gaps. Tutorial runs can now enter the
comparison panel, but only under an explicit short-clock boundary. The browser
test captures the exact variant run ID from the start request and polls that ID,
so an old `Run completed` message can no longer create a false pass.

## Verification

| Check | Result |
| --- | --- |
| Complete Python 3.10 suite | 370 run; 348 passed; 22 expected skips; 0 failed; 94.555 s |
| Frontend lint | passed |
| Production build | passed |
| Rendered HTML | 3/3 passed |
| Browser E2E | 11/11 passed, including 4/4 Castle tests |
| Responsive projects | desktop Chromium and Pixel 7 profile passed |
| Accessibility | no critical Castle findings; no critical/serious findings on checked installer and optional-result surfaces |
| Runtime path, secret and rights scan | passed; zero issues |
| Source release scan after commit | 763 members; zero forbidden and zero untracked release members |
| Retained Scheme C hashes | passed |
| Teaching PDF | six pages; all pages visually checked |

The 22 skips are recorded rather than hidden. They concern tests requiring the
separate verified UK data pack, the separately assembled public UK asset, or a
runtime guard that only applies outside the verified reference interpreter.
Castle does not depend on those assets.

## Stopwatch result

The clock began immediately before `start-value.cmd` and stopped after the
comparison download was saved. Startup and page load took 7.017 seconds. The
baseline finished at 12.869 seconds, the variant at 18.446 seconds, and the JSON
export at 19.694 seconds. The exported file was 12,574 bytes with SHA-256
`e34513c7ccdab7e1790291c2ac9c502d3b85efd5220413decce3b3bb36b28ab0`.

This automated run measures the software path, not a student's reading or
discussion time. It leaves ample mechanical headroom inside the 30-minute
lesson plan, but the unassisted novice target should still be observed with the
first student cohort.

## Presenter materials

- [English learner manual](../tutorial/CASTLE_101.md)
- [Chinese learner manual](../tutorial/CASTLE_101_ZH.md)
- [One-page checklist](../tutorial/CASTLE_101_QUICK_CARD.md)
- [Stuart demo runbook](../tutorial/STUART_DEMO_RUNBOOK.md)
- [Printable PDF](../../output/pdf/VALUE_Castle_101_guide.pdf)

Run `check-castle-demo.cmd` before leaving for the meeting. It checks the exact
Python runtime, website build, Castle pack, ports, disk and service ownership.
Then use `start-value.cmd` and `http://127.0.0.1:8800`. The site is intentionally
local; no cloud server or internet connection is needed for this demonstration.

## Remaining boundary

The result authorises Castle 101 as the first-run local teaching route. It does
not change the maturity of the real-UK data asset, optional network and water
features, annual GB baseline, or ten-year research scenarios. Their existing
release gates remain separate.

Machine-readable evidence:
`publication/prompt92-castle-101-release-report.json`.
