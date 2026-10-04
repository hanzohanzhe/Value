# Study Trash and Preflight Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add recoverable Study trash/restore behaviour and document the exact VALUE preflight resolution flow.

**Architecture:** Put filesystem moves, collision checks, audit records and legacy-trash discovery in a focused `gridform_core.study_lifecycle` service. Keep HTTP routing in `backend/server.py`, render the lifecycle through the existing React Study composer, and regenerate both PDFs from maintained Markdown sources.

**Tech Stack:** Python 3.10 standard library and unittest, TypeScript/React, ReportLab/PyPDF, Vite.

**Spec:** `docs/superpowers/specs/2026-08-25-study-trash-and-preflight-docs.md`

## Global Constraints

- Preserve all existing uncommitted VALUE 101 and network changes.
- Do not modify model science, solver behaviour, Study contracts, data values, or run results.
- Do not add permanent deletion, Data Pack deletion, or Module deletion.
- Do not run annual, two-year, ten-year, or complete Python test suites.
- Add only focused regression tests that catch lifecycle or UI contract failures.

---

### Task 1: Recoverable Study lifecycle service

**Files:**
- Create: `gridform_core/study_lifecycle.py`
- Create: `tests/test_study_lifecycle.py`

**Interfaces:**
- Produces: `list_study_trash(projects_root, runs_root, trash_root) -> list[dict[str, object]]`
- Produces: `move_study_to_trash(project_id, *, projects_root, runs_root, trash_root, confirmation_name=None, reason=None) -> dict[str, object]`
- Produces: `restore_study(trash_id, *, projects_root, trash_root) -> dict[str, object]`
- Produces: `study_id_is_reserved(project_id, *, projects_root, trash_root) -> bool`

- [ ] Write focused filesystem tests for no-run trash/restore, exact-name confirmation with historical Runs, active-Run refusal, ID reservation, revision preservation and legacy reset discovery.
- [ ] Run `python -m unittest tests.test_study_lifecycle -v` and confirm failures are caused by the missing lifecycle service.
- [ ] Implement atomic validated moves, one `trash-record.json` per new entry, rollback on move failure, legacy read compatibility and exact-path checks.
- [ ] Re-run `python -m unittest tests.test_study_lifecycle -v` until it passes.

### Task 2: Backend API and VALUE 101 reset integration

**Files:**
- Modify: `backend/server.py`
- Modify: `tests/test_prompt111_value_101_lifecycle.py`
- Modify: `tests/test_local_backend.py` only if its shared fixture must expose the new routes.

**Interfaces:**
- `GET /api/study-trash`
- `POST /api/projects/<project-id>/trash`
- `POST /api/study-trash/<trash-id>/restore`
- `/api/workspace` includes `study_trash` and annotates Runs with `source_study_status`.

- [ ] Add failing HTTP/lifecycle tests proving the routes, active-run block, confirmation policy, restore response, ID collision block and VALUE 101 reset reuse the shared service.
- [ ] Run only those named unittest methods and confirm the expected failures.
- [ ] Wire the service into project save, workspace presentation and VALUE 101 reset without changing run execution.
- [ ] Re-run the focused API and existing VALUE 101 reset tests.

### Task 3: Studies, Runs and Learn UI

**Files:**
- Modify: `app/page.tsx`
- Modify: `app/globals.css`
- Create or modify: the narrow existing frontend contract test under `tests/` that exercises VALUE 101 product wording.

**Interfaces:**
- `StudyComposer` consumes `studyTrash`, `onTrash`, and `onRestore` callbacks.
- Run presentation consumes `source_study_status` and disables derived actions for trashed sources.

- [ ] Add a failing focused frontend contract/render test for three-dot deletion, tiered confirmation, collapsed Trash, Restore, Learn baseline restore and run-source labelling.
- [ ] Run that test and confirm it fails because the controls are absent.
- [ ] Implement the smallest accessible UI, selection clearing, notices and disabled derived actions.
- [ ] Run the focused frontend test, `npm run lint`, and `npm run build` once after the UI is complete.

### Task 4: Check-readiness documentation and generated PDFs

**Files:**
- Modify: `docs/tutorial/VALUE_101.md`
- Modify: `docs/tutorial/VALUE_101_ZH.md`
- Modify: `docs/tutorial/VALUE_101_TO_VALUE_UK.md`
- Modify only if needed for source-driven layout: `scripts/build_value_101_pdf.py`
- Modify only if needed for source-driven layout: `scripts/build_value_101_to_value_uk_pdf.py`
- Regenerate: `output/pdf/VALUE_101_guide.pdf`
- Regenerate: `output/pdf/VALUE_101_TO_VALUE_UK_guide.pdf`
- Modify: `tests/test_prompt116_value_101_docs.py`

**Interfaces:**
- Documentation heading: `What Check readiness resolves`
- UI preflight label: `Network pack: Check readiness to confirm` before validation and `<pack-id> · verified` after success.

- [ ] Extend the existing documentation test with semantic requirements and PDF extracted-text checks; run it and confirm it fails before the prose/PDF update.
- [ ] Add the English/Chinese shared preflight flow, single-node/zonal distinction and compact comparison to the maintained Markdown sources.
- [ ] Correct the bounded UI wording in `app/page.tsx` without changing preflight logic.
- [ ] Regenerate both PDFs with `python scripts/build_value_101_pdf.py` and `python scripts/build_value_101_to_value_uk_pdf.py`.
- [ ] Re-run the focused documentation test and verify all required phrases appear in extracted PDF text.

### Task 5: Verification and review

**Files:**
- Review all changed files in `git diff`.

**Interfaces:**
- No new interface; validates Tasks 1–4 against the approved spec.

- [ ] Run the focused Study lifecycle/API/frontend/docs test commands from Tasks 1–4.
- [ ] Run frontend lint and production build with fresh output.
- [ ] Inspect `git diff --check` and confirm no model-science/data-result files changed for this feature.
- [ ] Request a code review against this spec, address Critical/Important findings, and re-run affected checks.
- [ ] Report exact evidence and remaining issues without rebuilding the Windows installer.
