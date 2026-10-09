// Explanations of known backend error codes (P1 W5, spec 3).  The code itself
// and the backend's message are never translated: the interface shows the
// explanation first, then "CODE: message" as sent.  Spread into en.ts; zh is
// errors.zh.ts with the same keys (tested).  GF_REQUEST_TIMEOUT and
// GF_RESPONSE_UNREADABLE are in en.ts, the two Study-ID codes in en/studies.ts.

export const errorsEn = {
  // ------------------------------------------------------------ Run lifecycle
  "errors.GF_RUN_EXECUTION_IDENTITY_CHANGED": "The installed modules, extensions or VALUE code changed after this Run was queued, so it did not start. Resubmit it to run with the current code.",
  "errors.GF_WORKER_EXITED": "The model worker stopped before it recorded a final state. Results of completed years stay readable; resume from the last verified annual checkpoint if one exists.",
  "errors.GF_WORKER_LOST": "The model worker is no longer running and the Run has no final state. Mark it lost to record it as failed, then resume it.",
  "errors.GF_WORKER_MARKED_LOST": "The model worker was marked lost after you confirmed it. The Run counts as failed and can be resumed from a verified annual checkpoint.",
  "errors.GF_WORKER_TERMINATED": "The model worker was terminated before the Run finished.",
  "errors.GF_WORKER_SPAWN_FAILED": "VALUE could not start the model worker for this Run. Check the environment with the doctor, then start the Run again.",
  "errors.GF_WORKER_ALIVE": "A model worker of this Run is still running; wait for it to stop before this action.",
  "errors.GF_RUN_CANCELLED_SAFE_BOUNDARY": "The Run was cancelled at a safe boundary on your request; years that finished before it stay readable.",
  "errors.GF_RUN_CANCELLED_BEFORE_WORKER": "The Run was cancelled before its model worker started; nothing was computed.",
  "errors.GF_RUN_PREPARATION_FAILED": "Preparing the Run (freezing its inputs) failed, so the model did not start. The message below names the cause.",
  "errors.GF_RUN_START_FAILED": "The Run could not be started. The message below names the cause; the Study is unchanged.",
  "errors.GF_INPUT_SNAPSHOT_FAILED": "The Run's input snapshot could not be frozen, so the model did not start.",
  "errors.GF_RUN_RESERVATION_LOCK_TIMEOUT": "VALUE was busy with another change to the same records; start the Run again shortly.",
  "errors.GF_LOCK_TIMEOUT": "VALUE was busy with another change to the same records; retry shortly.",
  "errors.GF_RUN_START_STUDY_CHANGED": "The Study changed after the readiness check. Check readiness again before starting the Run.",
  "errors.GF_PREFLIGHT_REFUSED": "The readiness check found an error, so the Run was not started. Fix the listed issue, then check readiness again.",
  "errors.GF_RUN_SOURCE_STUDY_MISSING": "The Study this Run came from no longer exists; the Run's results stay readable.",
  "errors.GF_RUN_SOURCE_STUDY_IN_TRASH": "The Study this Run came from is in trash. Restore it before resuming or creating Runs from it.",
  "errors.GF_RUN_NOT_TERMINAL": "The Run is still active; cancel it before this action.",
  "errors.GF_RUN_NOT_FOUND": "VALUE has no Run with this ID; it may have been removed.",

  // ------------------------------------------------- validation and publication
  "errors.GF_VALIDATION_GATE_FAILED": "A validation gate (run invariants, energy balance or storage limits) failed, so annual results are not published.",
  "errors.GF_VALIDATION_CONTRACT_OR_MECHANISM": "A required contract or analytical-invariant check failed, so annual results are not published.",
  "errors.GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED": "A raw invariant of this reproduction Run failed, so its annual results are not published on result pages; Inspect and exports keep them.",

  // ----------------------------------------------------- Studies and revisions
  "errors.GF_STUDY_INVALID": "The Study settings were refused. The message below names the setting to correct.",
  "errors.GF_PROJECT_REVISION": "The Study was saved elsewhere since you opened it. Reload it and apply your change again.",
  "errors.GF_STUDY_TRASH_CONFIRMATION_REQUIRED": "Moving a Study to trash needs its exact name as confirmation.",
  "errors.GF_SOLVER_CONTRACT_ACK_REQUIRED": "A custom solver contract must be acknowledged before the Study is saved.",

  // ------------------------------------------------- modules and extensions
  "errors.GF_MODULE_QUARANTINED": "A selected module is quarantined because its files failed a check. Repair or remove it in Modules before running.",
  "errors.GF_MODULE_NOT_READY": "One or more selected modules are not ready to run. Modules lists what each one needs.",
  "errors.GF_MODULE_TRUST_REQUIRED": "Installing a module runs its Python code. Confirm that the bundle comes from a source you trust.",
  "errors.GF_MODULE_IN_USE": "The module is used by a saved Study or Run, so it cannot be changed this way.",
  "errors.GF_MODULE_LIFECYCLE_RUNS_PENDING": "Runs that use this code have not finished. Confirm to change the installed code anyway; queued Runs then stop before they start.",
  "errors.GF_MODULE_CATALOG_STALE": "The module catalogue could not be refreshed; rescan modules before starting Runs.",
  "errors.GF_EXTENSION_IN_USE": "The extension is selected by a saved Study or Run, so it cannot be changed this way.",
  "errors.GF_EXTENSION_TRUST_REQUIRED": "Installing an extension runs its Python code. Confirm that the bundle comes from a source you trust.",
  "errors.GF_PREFLIGHT_MODULE_SOURCE_CHANGED": "A module's source files changed after it was installed. Review the change before relying on its results.",

  // ---------------------------------------------------------------- data
  "errors.GF_DATA_PACK_UNKNOWN": "VALUE has no data pack with this ID; it may not be installed.",
  "errors.GF_DATA_BUNDLE_RIGHTS_ACK": "Acknowledge the data licence and attribution before installing the data pack.",
  "errors.GF_DATA_PACK_FREEZING": "This data pack is being frozen for a Run that is starting; try again when the Run has started.",
  "errors.GF_UPLOAD_SIZE": "The file is empty or larger than the upload limit.",
  "errors.GF_MAPPING_FX": "A price column in euros needs the exchange rate, its basis and year before it can be previewed.",

  // ------------------------------------------------------- local session
  "errors.GF_SESSION_REQUIRED": "This page was not opened through the VALUE launcher. Start VALUE with its launcher.",
  "errors.GF_SESSION_INVALID": "The page's session no longer matches the running VALUE. Restart VALUE with its launcher.",
  "errors.GF_HOST_REJECTED": "VALUE only answers requests addressed to 127.0.0.1 or localhost on its own port.",
} as const;
