# Prompt 113: controlled VALUE 101 experiments

## Purpose

Teach causal comparison by allowing one data-pack change or one storage-pricing
module change while preserving the rest of the baseline Study.

## Implemented contract

- The learner chooses either `Windy` or `High demand`; the UI does not silently
  choose a variant.
- Before saving, the clone endpoint performs a dry run and returns the changed
  dimension, exact affected data roles, deterministic transformation and the
  dimensions held fixed.
- Windy changes only `weather.wind`, `profiles.vre_onshore` and
  `profiles.vre_offshore`. High demand changes only `demand.real` and
  `demand.forecast`.
- The guided storage experiment exposes only dynamic annual-average recovery
  and the retained legacy fixed tariff. Other installed storage-cost modules
  remain available in the ordinary Study composer, not in this controlled
  lesson.
- Storage preview changes only `modules.storage_cost`; all data, years,
  parameters, runtime controls and non-storage modules are preserved.
- Selection, preview, Study creation and Run launch are four separate actions.
  No selection event starts computation.

## Verification

- `test_prompt113_value_101_experiments.py`
- Prompt 111 lifecycle regression
- frontend lint, production build and rendered-output regression

All results retain the teaching-only, non-annual scientific boundary.
