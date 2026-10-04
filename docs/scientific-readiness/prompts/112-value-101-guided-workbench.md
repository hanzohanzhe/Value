# Prompt 112: guided VALUE 101 workbench

## Purpose

Replace the obsolete teaching-page presentation with a first-use route that
shows how the ordinary VALUE workbench is assembled. The teaching UI must not
hide a separate solver behind simplified controls.

## Implemented contract

- Home presents four distinct actions: start VALUE 101, build a Study, open a
  saved Study, or add data/modules.
- The Learn page contains seven independently accessible steps and an in-page
  five-building-block lesson. Browser progress is presentation state only.
- Baseline Study creation and Run launch are separate operations.
- The baseline displays exactly seven module cards using identity, version,
  contract, inputs, outputs and implementation locations supplied by the live
  module registry.
- `Build from VALUE 101` loads an ordinary unsaved Study draft and does not copy
  teaching lifecycle metadata.
- Incompatible module choices remain visible in Advanced mode with the backend
  reason and a corrective action; they cannot be selected.
- Experimental AC feasibility is not offered as an ordinary first-use path.
  The optional public network lesson is the fixed zonal transport/redispatch
  method.

## Verification

- `test_prompt112_value_101_frontend.py`
- migrated Prompt 91 launcher/lesson regression
- frontend lint and production build
- production-bundle rendered HTML regression

The workbench contract is bounded to teaching and configuration visibility. It
does not promote VALUE 101 output to annual British scientific evidence.
