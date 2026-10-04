# Castle 101 teaching design

Date: 20 August 2026  
Approved scope: Prompts 85 to 92  
Product identity: VALUE Network Extensions 0.6 development line

## Purpose

Castle 101 is the first-run teaching route for VALUE. A person who has already
installed the application must be able to start it, run a small real model,
change one modelling choice, compare the two runs and explain the main result in
30 minutes. The exercise uses the same backend, module registry, Study revision
and result artifacts as an ordinary VALUE study.

Castle 101 is not a second simulator and does not use precomputed result cards.
The browser must never invent a bid, dispatch quantity, planning event, cost or
carbon value.

## Release priority

The teaching model, guided workflow and teaching manual are the first remaining
pre-publication product gate. Optional network, AC, hydrology and transmission
expansion code stays installed but does not enter the Castle 101 path. No real
network data is bundled or requested.

## Thirty-minute contract

The clock starts when the user double-clicks `start-value.cmd`. Installation is
measured separately.

| Elapsed time | Learner outcome |
| --- | --- |
| 0 to 3 minutes | Open the local site and enter Learn |
| 3 to 7 minutes | Identify Data, Study, Modules, Run and Results |
| 7 to 12 minutes | Inspect the Castle system and launch its real baseline |
| 12 to 20 minutes | Read dispatch, bids, curtailment, storage, cost, carbon and planning evidence |
| 20 to 25 minutes | Clone the Study and change the storage pricing module |
| 25 to 29 minutes | Run and compare the controlled variant |
| 29 to 30 minutes | Export the result and locate the advanced 101 guides |

No mandatory step may require a terminal, internet connection, manual JSON edit
or browsing the repository.

## Castle data and model boundary

The new checked-in pack ID is `force-castle-101-v1`. It is separate from
`force-synthetic-contract-pack-v1`, which remains the contract and CI fixture.
Every Castle object is synthetic and released under CC0-1.0.

Castle is a single-node teaching system with 48 half-hour periods in each of two
model years. It contains:

- a morning and evening demand pattern;
- operational solar and onshore wind;
- one CCGT fleet entry;
- one priced external import offer, with unused import roles present at zero;
- one 1C battery with explicit MW, MWh and efficiency data;
- one planning project whose deterministic timeline is visible in year two;
- synthetic CAPEX, FOM, fuel, carbon and planning records.

The pack is tuned to produce observable renewable allocation, some unused VRE,
storage charging and discharge, thermal or import competition, non-zero cost and
carbon, and an auditable project transition. Tests assert the physical and
accounting identities rather than a screenshot.

## Teaching run policy

Add a run policy named `tutorial`:

- 48 half-hour periods per year;
- exactly two configured years;
- `annual_economics_candidate=false`;
- `scientific_baseline_candidate=false`;
- no annual or national claim;
- normal immutable input snapshot, module resolution and result validation.

Every tutorial result displays `Teaching diagnostic: not annual economics`.
Full-year and complete-study modes remain unchanged.

## First-run experience

Add `Learn` as navigation item 00. On first use it presents five plain-language
concepts and a system card for Castle. `Load Castle 101` selects the installed
pack and fills the existing Study composer with a two-year, single-node,
bid-at-cost Study. The learner reviews and saves the ordinary Study revision.

The Learn view tracks local progress without changing scientific identity. It
links to the existing Data, Studies, Runs, Market replay, VRE and curtailment,
Inspect and comparison views. The tutorial never substitutes a browser-side
calculation for these screens.

The required experiment clones the completed baseline through the existing
controlled storage-policy clone service. One Study uses dynamic annual-average
storage recovery and the other uses the legacy tariff. The comparison screen
must state what changed and refuse a causal claim if other scientific dimensions
also changed.

Tutorial reset removes only local progress and tutorial-created drafts. It must
not delete completed runs, data packs or unrelated Studies.

## Code structure

Do not add the Learn implementation to the existing monolithic page body.
Create focused files under `app/features/learn/` for the tutorial copy, progress
and view component. `app/page.tsx` owns navigation and passes existing actions.

Pack generation and validation live outside the Scheme C compatibility tree.
The retained Scheme C source and hashes must not change.

## Documentation

Produce:

- `docs/tutorial/CASTLE_101.md`, the English learner manual;
- `docs/tutorial/CASTLE_101_ZH.md`, the Chinese learner manual;
- `docs/tutorial/STUART_DEMO_RUNBOOK.md`, a short presenter script;
- `docs/tutorial/CASTLE_101_QUICK_CARD.md`, a one-page checklist;
- `output/pdf/VALUE_Castle_101_guide.pdf`, the visually checked English handout.

The English manual is written for an intelligent reader who may not know power
system modelling. It explains what to click, what the model just calculated and
which conclusions are out of scope. After technical review, run the humanizer
file workflow. Preserve facts, commands, identifiers and links. The final text
uses plain English, varied sentence length and no promotional language.

The PDF uses a restrained university-handout layout, readable type, page
numbers, stable headings and no decorative cover copy. Render every page to PNG
and inspect it before delivery.

## Installation and local demo

The normal installer installs both the contract fixture and Castle pack
idempotently. Existing data is not replaced. The local site continues to bind to
`127.0.0.1:8800`; the API remains on `127.0.0.1:8766`.

For the presenter laptop, a preflight script verifies the runtime, Castle pack,
ports, build and writable state directory. The demo must work after the network
connection is disabled.

## Acceptance gates

1. Pack manifest, all required roles and CC0 records validate.
2. A real two-year tutorial run completes through selected PSM and CEM modules.
3. Energy balance, SOC, cost and carbon ledgers reconcile.
4. Castle produces the intended visible teaching events without hard-coded UI
   results.
5. The controlled storage-policy clone changes one scientific dimension only.
6. The required browser journey completes without terminal use.
7. Critical accessibility violations are zero at desktop and laptop widths.
8. Frontend lint, production build, rendered tests and the complete Python suite
   pass.
9. Retained Scheme C hashes remain unchanged.
10. A timed dry run records each step and completes inside 30 minutes.

## Explicit non-goals

- real Great Britain conclusions;
- annual economics from 48 periods;
- real transmission, AC, hydrology or expansion data;
- a new solver or a new CEM method;
- a public cloud service;
- automatic deletion of research records;
- replacing the advanced Build Your Own Model 101 or Module Developer 101.

