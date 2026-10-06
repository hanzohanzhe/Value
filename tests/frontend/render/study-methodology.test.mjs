import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// Spec 7 (X0 S11/S12, Q3, Q13) rendered offline: the composer's Methodology
// radio with whitelist disabling, the code-identity line and the native
// <dialog> that confirms a method change.
const COMPOSER = "app/features/studies/StudyComposer.tsx";
const DIALOG = "app/features/studies/StudyMigrationDialog.tsx";

const catalogue = {
  default_profile_id: "value-corrected",
  profiles: [
    { id: "value-corrected", label: "Corrected methodology (default)", frozen: false, default: true, supported_data_packs: "*", supported_extensions: "*" },
    { id: "doctoral-lineage-0.6.0a2", label: "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)", frozen: true, default: false, supported_extensions: [],
      supported_data_packs: [{ id: "value-101-baseline-v1", label: "VALUE 101 baseline", pack_class: "teaching" }] },
  ],
};
const workspace = {
  architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [],
  data_packs: [{ id: "value-101-baseline-v1", name: "VALUE 101 baseline" }, { id: "my-pack", name: "My own pack" }],
  module_installations: [], extension_installations: [], projects: [], study_trash: [], runs: [], runtime: { python: "3.10", compatible: true },
};
const form = { name: "S", purpose: "", start_year: 2025, end_year: 2026, modules: { psm: "value-bid-at-cost-psm" }, selected_extensions: [], extension_parameters: {}, maturity_acknowledgements: {}, market_configuration: {} };
const noop = () => {};
const composerProps = (profileId, extra = {}) => ({
  workspace, form, selectedPackId: "value-101-baseline-v1", resolution: null, resolving: false, resolutionError: "",
  savedProjects: [], studyTrash: [], selectedProjectId: "", assumptions: null,
  onForm: noop, onPack: noop, onDomain: noop, onExtension: noop, onModule: noop, onExtensionParameter: noop, onAcknowledgement: noop,
  onSave: noop, onLoad: noop, onOpenRun: noop, onTrash: noop, onRestore: noop, onOpenTrashRuns: noop, onOpenData: noop,
  traceLevel: "summary", onTraceLevel: noop, methodology: { catalogue, profileId }, onMethodology: noop, ...extra,
});

test("the Methodology radio offers the two spec options; corrected leaves every data pack available", async () => {
  const html = await renderTsx(COMPOSER, "default", composerProps("value-corrected"));
  const text = textOf(html);
  assert.match(text, /Methodology Corrected \(default\) Doctoral reproduction Locks thesis-era reference settings: legacy storage tariff, doctoral carbon factors, thesis-era modules and data packs only\. External code is not allowed\./);
  assert.match(html, /<input type="radio" name="study-methodology" checked="" value="value-corrected"\/>/);
  assert.doesNotMatch(html, /<option[^>]*disabled=""/);
  assert.doesNotMatch(text, /not available with this methodology/);
});

test("doctoral disables the data packs outside its whitelist and says why", async () => {
  const html = await renderTsx(COMPOSER, "default", composerProps("doctoral-lineage-0.6.0a2"));
  const text = textOf(html);
  assert.match(html, /name="study-methodology" checked="" value="doctoral-lineage-0\.6\.0a2"/);
  assert.match(html, /<option value="my-pack" disabled="">My own pack · not available with this methodology<\/option>/);
  assert.match(html, /<option value="value-101-baseline-v1"(?: selected="")?>VALUE 101 baseline<\/option>/);
  assert.match(text, /Doctoral reproduction uses thesis-era data packs only \(VALUE 101 baseline\)\. Unavailable: My own pack\./);
});

test("without a catalogue the composer says so instead of offering a guess", async () => {
  const text = textOf(await renderTsx(COMPOSER, "default", composerProps(null, { methodology: { catalogue: null, profileId: null, error: "HTTP 500" } })));
  assert.match(text, /Methodology profiles could not be loaded \(HTTP 500\)\. The server applies its default methodology unless this Study names one\./);
});

test("a saved Study re-identified for code only shows one info line", async () => {
  const project = { id: "p", name: "Saved", data_pack_id: "value-101-baseline-v1", start_year: 2025, end_year: 2026, modules: {}, updated_at: "", revision_number: 3, revision_sha256: "0123456789abcdef0123", revision_reason: "code-identity-upgrade" };
  const html = await renderTsx(COMPOSER, "default", composerProps("value-corrected", { savedProjects: [project] }));
  assert.match(textOf(html), /Updated to code identity 0123456789ab \(no change to methods or results expected\)/);
  const saved = await renderTsx(COMPOSER, "default", composerProps("value-corrected", { savedProjects: [{ ...project, revision_reason: "user-save" }] }));
  assert.doesNotMatch(textOf(saved), /Updated to code identity/);
});

const migration = {
  classification: "method_upgrade_required", automatic: false, confirmable: true, diff_sha256: "d1", selected_profile_id: "doctoral-lineage-0.6.0a2",
  differences: [
    { dimension: "methodology", key: "profile_id", old: null, new: "doctoral-lineage-0.6.0a2", classification: "method_upgrade_required", effect: "The Study predates methodology profiles; confirming records the selected methodology explicitly (Q13)." },
    { dimension: "solver_contract", key: "contract_version", old: "v3", new: "v4", classification: "method_upgrade_required", effect: "The solver contract changed." },
  ],
  profile_choices: [
    { profile_id: "value-corrected", label: "Corrected methodology (default)", default: true, frozen: false, supported: true, unsupported_reasons: [], matches_reference_preset: false },
    { profile_id: "doctoral-lineage-0.6.0a2", label: "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)", default: false, frozen: true, supported: false, unsupported_reasons: ["data_pack"], matches_reference_preset: false },
  ],
};

test("the migration dialog: native dialog, focusable title, version sentence, diff rows and both buttons", async () => {
  const html = await renderTsx(DIALOG, "default", { projectId: "p", studyName: "Golden D1", migration, version: "0.7.0a1", onCancel: noop, onSaved: noop });
  const text = textOf(html);
  assert.match(html, /^<dialog class="study-migration-dialog value-new-control" aria-labelledby="study-migration-title">/);
  assert.match(html, /<h2 id="study-migration-title" tabindex="-1">This Study needs your confirmation before it runs<\/h2>/);
  assert.match(text, /VALUE 0\.7\.0a1 changes how this Study is computed:/);
  assert.match(text, /Methodology profile id not recorded → Doctoral reproduction \(as implemented in VALUE 0\.6\.0-alpha\.2\)/);
  assert.match(text, /Solver contract contract version v3 → v4 The solver contract changed\./);
  assert.match(text, /Review and save as new revision Cancel$/);
  assert.match(html, /<input type="radio" disabled="" name="migration-methodology" checked="" value="doctoral-lineage-0\.6\.0a2"\/>/);
  assert.match(text, /Not available for this Study: data pack\./);
});

test("without profile choices or a version the dialog lists only the diff", async () => {
  const html = await renderTsx(DIALOG, "default", { projectId: "p", migration: { ...migration, profile_choices: undefined }, onCancel: noop, onSaved: noop });
  assert.match(textOf(html), /The installed VALUE changes how this Study is computed:/);
  assert.doesNotMatch(html, /migration-methodology/);
});
