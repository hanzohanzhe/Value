// English interface messages (default language, P1 spec 3).
//
// Keys are namespaced by feature ("nav.*", "service.*", "runs.results.*").
// zh.ts must have exactly the same keys and the same {placeholders}
// (tests/frontend/unit/i18n.test.mjs).  Pages not yet moved to the
// dictionaries keep their English text in place until W4/W5.
//
// Page groups keep their messages in app/i18n/pages/*.en.ts (P1 W4b: Data,
// Modules, Extensions), spread in here so there is still one dictionary.
import { dataEn } from "./pages/data.en.ts";
import { dataWorkbenchEn } from "./pages/dataWorkbench.en.ts";
import { modulesEn } from "./pages/modules.en.ts";

import { homeEn } from "./en/home.ts";
import { journeyEn } from "./en/journey.ts";
import { learnEn } from "./en/learn.ts";
import { studiesEn } from "./en/studies.ts";

import { resultPagesEn } from "./messages/resultPages.en.ts";
import { networkEn } from "./messages/network.en.ts";
import { marketEn } from "./messages/market.en.ts";
import { runViewsEn } from "./messages/runViews.en.ts";
import { evidenceEn } from "./messages/evidence.en.ts";
import { workspaceEn } from "./messages/workspace.en.ts";
import { errorsEn } from "./messages/errors.en.ts";
import { viewModelsEn } from "./messages/viewModels.en.ts";

export const en = {
  // Pages of W4a (P1 spec 6.1, 6.2), one file per page: Home, Learn, Research guide, Studies.
  ...homeEn, ...learnEn, ...journeyEn, ...studiesEn,

  // ---------------------------------------------------------------- language
  "locale.label": "Language",
  "locale.en": "English",
  "locale.zh": "中文",

  // ------------------------------------------------------------------ shell
  "shell.brand.mark": "VA",
  "shell.brand.name": "VALUE",
  "shell.brand.tagline": "Power-system evolution",
  "shell.contract": "Contract {version}",
  "shell.version": "VALUE {version}",

  // ------------------------------------------------------------- navigation
  "nav.label": "Workspace",
  "nav.item": "{label}: {note}",
  "nav.group.start": "Start",
  "nav.group.work": "Work",
  "nav.group.results": "Results",
  "nav.journey.label": "Research guide",
  "nav.journey.note": "Reproduce or change data",
  "nav.learn.label": "Learn",
  "nav.learn.note": "VALUE 101",
  "nav.overview.label": "Home",
  "nav.overview.note": "Study status",
  "nav.data.label": "Data",
  "nav.data.note": "Inputs and mappings",
  "nav.models.label": "Modules",
  "nav.models.note": "PSM and CEM",
  "nav.projects.label": "Studies",
  "nav.projects.note": "Scenarios and settings",
  "nav.run.label": "Runs",
  "nav.run.note": "Launch and results",
  "nav.marketReplay.label": "Market replay",
  "nav.marketReplay.note": "Bids and dispatch",
  "nav.curtailment.label": "VRE & curtailment",
  "nav.curtailment.note": "Unused renewable energy",
  "nav.networkRedispatch.label": "Network & redispatch",
  "nav.networkRedispatch.note": "Congestion and balancing",
  "nav.systems.label": "Network & water",
  "nav.systems.note": "Optional-domain results",
  "nav.audit.label": "Inspect",
  "nav.audit.note": "Ledgers and planning",
  "nav.compare.label": "Compare",
  "nav.compare.note": "Runs side by side",
  "nav.extend.label": "Extensions",
  "nav.extend.note": "Catalogue and authoring",
  "nav.runSection": "Pages of this Run",
  "nav.runResults": "Annual results",
  "nav.openMenu": "Open navigation",
  "nav.closeMenu": "Close navigation",
  "shell.skipToMain": "Skip to main content",
  "shell.sidebar": "Sidebar",

  // ---------------------------------------------------------- service status
  "service.loading.title": "Connecting to model service…",
  "service.loading.detail": "Checking the local API",
  "service.online.title": "Python {version}",
  "service.online.ready": "{capability} ready",
  "service.online.runtimeUnavailable": "VALUE native runtime unavailable",
  "service.degraded.title": "● Backend degraded",
  "service.degraded.failed": "{count, plural, one {The last request failed} other {The last # requests failed}}; retrying in {seconds} s",
  "service.degraded.reduced": "Running with reduced capability: {reasons}",
  "service.degraded.seeModules": "see Modules",
  "service.offline.title": "● Backend offline",
  "service.offline.detail": "No answer after {attempts} attempts. Start VALUE from its launcher, then retry",
  "service.retry": "Retry",

  // ---------------------------------------------------------------- header
  "header.breadcrumb": "VALUE / {group}",
  "header.draftPack": "Draft data pack",
  "header.draftPackSelect": "Selected data pack",
  "header.studyPack": "Data pack of the selected Study",
  "header.studyPackTitle": "The data pack this saved Study runs on. The draft data pack for a new Study is chosen in Studies.",
  "header.baseInputsTitle": "Required base roles of this data pack. A Study's extension roles are counted in the Data page's input contract.",
  "header.backgroundRuns": "{count, plural, one {● # Run running in background} other {● # Runs running in background}}",
  "header.readMe": "Read me",
  "header.studyDisclosure": "Study: {name}",
  "header.pill.notLoaded": "Inputs not loaded",
  "header.pill.noPack": "No data pack",
  "header.pill.ready": "{valid} of {required} base inputs ready",

  // ------------------------------------------------------- contract version
  "contract.mismatch.title": "The interface and the local service are different versions. Restart VALUE.",
  "contract.mismatch.detail": "Interface contract {expected}; local service contract {actual}.",
  "contract.mismatch.notReported": "not reported",
  "contract.mismatch.reload": "Reload the page",

  // ------------------------------------------- error-code explanations (spec 3)
  "errors.GF_REQUEST_TIMEOUT": "The local service did not answer in time. It may still be working: refresh later before repeating the action.",
  "errors.GF_RESPONSE_UNREADABLE": "The local service sent an answer the interface cannot read.",

  // ------------------------------------------------ shared components (app/ui)
  "ui.loading": "Loading",
  "ui.working": "Working",
  "ui.close": "Close",
  "ui.cancel": "Cancel",
  "ui.confirm": "Confirm",
  "ui.copy": "Copy",
  "ui.copied": "Copied",
  "ui.copyFailed": "Copy failed",
  "ui.copyFullValue": "Copy full value",
  "ui.dismiss": "Dismiss",
  "ui.showDataTable": "Show data table",
  "ui.hideDataTable": "Hide data table",
  "ui.chooseFile": "Choose a file or drop it here",
  "ui.noFileChosen": "No file chosen",
  "ui.scrollTable": "Scrollable table",
  "ui.numberRequired": "Enter a number",
  "ui.numberNotNumeric": "Not a number",
  "ui.numberBelowMin": "Must be at least {min}",
  "ui.numberAboveMax": "Must be at most {max}",
  "ui.numberStep": "Must be a multiple of {step}",
  "ui.steps": "Steps",

  // ------------------------------------- Data, Modules, Extensions (P1 W4b)
  ...dataEn,
  ...dataWorkbenchEn,
  ...modulesEn,
  // ------------------------------------- result pages (W4c, spec 6.5/6.6)
  ...resultPagesEn,
  // ------------------------------------- remaining result views (W5, spec 3)
  ...networkEn,
  ...marketEn,
  ...runViewsEn,
  ...evidenceEn,
  ...workspaceEn,
  // ------------------------------- known backend error codes (W5, spec 3)
  ...errorsEn,
  // ------------------------------- pure view code (W5, active language)
  ...viewModelsEn,
} as const;

export type MessageKey = keyof typeof en;
