import assert from "node:assert/strict";
import test from "node:test";
import {
  PROFILE_PARAMETER, applyProfileChoice, dataPackAvailability, extensionAvailability, isMethodologyCatalogue,
  moduleAvailability, profileOptionDescription, profileOptionLabel, selectedProfileId,
} from "../../../app/features/studies/methodologyChoice.ts";
import {
  codeIdentityUpdate, migrationFromResponse, migrationRows, migrationValueText, needsConfirmation, preferredMigrationProfile,
} from "../../../app/features/studies/studyMigration.ts";

// Spec 7 / plan X0 S11–S12 / DECISIONS Q3, Q13 and F-X0-2.
const catalogue = {
  schema_version: "value.methodology-catalogue/v1",
  default_profile_id: "value-corrected",
  profiles: [
    { id: "value-corrected", label: "Corrected methodology (default)", frozen: false, default: true, supported_modules: "*", supported_extensions: "*", supported_data_packs: "*", reference_configuration: { modules: {}, parameters: {} } },
    {
      id: "doctoral-lineage-0.6.0a2", label: "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)", frozen: true, default: false,
      supported_extensions: [],
      supported_data_packs: [
        { id: "value-uk-open-data-pack-v1", label: "GBP1 public1", pack_class: "scientific_reference", manifest_sha256: ["a"] },
        { id: "value-101-baseline-v1", label: "VALUE 101 baseline", pack_class: "teaching", manifest_sha256: ["b"] },
      ],
      reference_configuration: { modules: { storage_cost: "value-legacy-storage-tariff" }, parameters: { "carbon.factor_scenario": "doctoral_reproduction_2026_07_18" } },
    },
  ],
};
const [correctedProfile, doctoralProfile] = catalogue.profiles;

test("the composer offers 'Corrected methodology (default)' and 'Doctoral reproduction' with the spec description", () => {
  assert.equal(isMethodologyCatalogue(catalogue), true);
  assert.equal(isMethodologyCatalogue({ profiles: [] }), false);
  assert.equal(profileOptionLabel(correctedProfile), "Corrected methodology (default)");
  assert.equal(profileOptionLabel(doctoralProfile), "Doctoral reproduction");
  assert.equal(profileOptionDescription(correctedProfile), null);
  assert.equal(profileOptionDescription(doctoralProfile), "Locks thesis-era reference settings: legacy storage tariff, doctoral carbon factors, thesis-era modules and data packs only. External code is not allowed.");
});

test("the selected profile is the explicit parameter, else the catalogue default", () => {
  assert.equal(selectedProfileId({}, catalogue), "value-corrected");
  assert.equal(selectedProfileId({ [PROFILE_PARAMETER]: "doctoral-lineage-0.6.0a2" }, catalogue), "doctoral-lineage-0.6.0a2");
  assert.equal(selectedProfileId({}, null), null);
});

test("doctoral pre-disables data packs it does not list and every extension; corrected disables nothing", () => {
  assert.deepEqual(dataPackAvailability(correctedProfile, "anything"), { available: true });
  assert.deepEqual(dataPackAvailability(doctoralProfile, "value-101-baseline-v1"), { available: true });
  const blocked = dataPackAvailability(doctoralProfile, "my-copy-of-value-uk");
  assert.equal(blocked.available, false);
  assert.equal(blocked.reason, "Doctoral reproduction uses thesis-era data packs only (GBP1 public1, VALUE 101 baseline).");
  assert.equal(extensionAvailability(doctoralProfile, "value-hydrology").available, false);
  assert.equal(extensionAvailability(correctedProfile, "value-hydrology").available, true);
  assert.deepEqual(moduleAvailability({ methodology_supported: true }, doctoralProfile), { available: true });
  assert.deepEqual(moduleAvailability({}, doctoralProfile), { available: true }, "no server verdict: the server decides at resolution");
  assert.deepEqual(moduleAvailability({ methodology_supported: false, methodology_reason: "staged PSM is VALUE-added" }, doctoralProfile), { available: false, reason: "staged PSM is VALUE-added" });
});

test("choosing doctoral writes its reference preset explicitly (Q3); going back removes only the preset values", () => {
  const draft = { parameters: { "planning.rate": 0.1 }, modules: { psm: "value-bid-at-cost-psm", storage_cost: "dynamic-annual-storage-cost" } };
  const reproduction = applyProfileChoice(draft, "doctoral-lineage-0.6.0a2", catalogue);
  assert.deepEqual(reproduction.parameters, { "planning.rate": 0.1, [PROFILE_PARAMETER]: "doctoral-lineage-0.6.0a2", "carbon.factor_scenario": "doctoral_reproduction_2026_07_18" });
  assert.equal(reproduction.modules.storage_cost, "value-legacy-storage-tariff");
  assert.deepEqual(draft.parameters, { "planning.rate": 0.1 }, "the input is not mutated");
  const back = applyProfileChoice(reproduction, "value-corrected", catalogue);
  assert.deepEqual(back.parameters, { "planning.rate": 0.1, [PROFILE_PARAMETER]: "value-corrected" });
  assert.equal(back.modules.storage_cost, "value-legacy-storage-tariff", "modules stay as the user left them");
  const customised = applyProfileChoice({ ...reproduction, parameters: { ...reproduction.parameters, "carbon.factor_scenario": "custom" } }, "value-corrected", catalogue);
  assert.equal(customised.parameters["carbon.factor_scenario"], "custom");
  const coOptimised = applyProfileChoice({ parameters: {}, modules: { psm: "pf" } }, "doctoral-lineage-0.6.0a2", catalogue);
  assert.equal("storage_cost" in coOptimised.modules, false, "a slot the draft does not use is not created");
});

const methodUpgrade = {
  schema_version: "value.revision-classification/v1", classification: "method_upgrade_required", automatic: false, confirmable: true,
  diff_sha256: "d1", selected_profile_id: "value-corrected",
  differences: [
    { dimension: "methodology", key: "profile_id", old: null, new: "value-corrected", classification: "method_upgrade_required", effect: "The Study predates methodology profiles.", hint: "matches_reference_preset", matches_reference_preset: ["doctoral-lineage-0.6.0a2"] },
    { dimension: "module", key: "psm:value-bid-at-cost-psm", old: "5.1.0", new: "5.2.0", classification: "method_upgrade_required", effect: "requires user opt-in" },
  ],
  profile_choices: [
    { profile_id: "value-corrected", label: "Corrected methodology (default)", default: true, frozen: false, supported: true, unsupported_reasons: [], matches_reference_preset: false },
    { profile_id: "doctoral-lineage-0.6.0a2", label: "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)", default: false, frozen: true, supported: true, unsupported_reasons: [], matches_reference_preset: true },
  ],
};

test("only confirmable, non-automatic classifications open the dialog", () => {
  assert.equal(needsConfirmation(methodUpgrade), true);
  assert.equal(needsConfirmation({ ...methodUpgrade, classification: "code_identity_upgrade", automatic: true, confirmable: false }), false);
  assert.equal(needsConfirmation({ ...methodUpgrade, classification: "content_changed", confirmable: false }), false);
  assert.equal(migrationFromResponse({ error: "x", revision_migration: methodUpgrade }), methodUpgrade);
  assert.equal(migrationFromResponse({ accepted: false, checks: { project_revision: { classification: methodUpgrade } } }), methodUpgrade);
  assert.equal(migrationFromResponse({ accepted: true, checks: { project_revision: { classification: null } } }), null);
  assert.equal(migrationFromResponse(null), null);
});

test("the diff rows state dimension, old → new and the effect; missing values say not recorded", () => {
  const rows = migrationRows(methodUpgrade);
  assert.deepEqual(rows.map(({ dimension, subject, before, after }) => [dimension, subject, before, after]), [
    ["Methodology", "profile id", "not recorded", "Corrected methodology (default)"],
    ["Module", "psm:value-bid-at-cost-psm", "5.1.0", "5.2.0"],
  ]);
  assert.equal(rows[1].effect, "requires user opt-in");
  assert.equal(migrationValueText(["a", "b", "c", "d"]), "4 items");
  assert.equal(migrationValueText({ profile_id: "value-corrected" }, "methodology", methodUpgrade.profile_choices), "Corrected methodology (default)");
  assert.equal(migrationValueText({ contract_version: "v4" }), "v4");
  assert.equal(migrationValueText([]), "none");
});

test("F-X0-2: a Study that matches the doctoral reference preset opens on that profile", () => {
  assert.equal(preferredMigrationProfile(methodUpgrade), "doctoral-lineage-0.6.0a2");
  const unsupported = { ...methodUpgrade, profile_choices: methodUpgrade.profile_choices.map((choice) => choice.frozen ? { ...choice, supported: false, matches_reference_preset: false } : choice) };
  assert.equal(preferredMigrationProfile(unsupported), "value-corrected");
  assert.equal(preferredMigrationProfile({ ...methodUpgrade, profile_choices: undefined }), null);
});

test("a code-only revision gets the one-line info; any other reason gets none", () => {
  assert.equal(codeIdentityUpdate({ revision_reason: "code-identity-upgrade", revision_sha256: "0123456789abcdef0123" }), "Updated to code identity 0123456789ab (no change to methods or results expected)");
  assert.equal(codeIdentityUpdate({ revision_reason: "environment-reidentify", revision_sha256: "abcdefabcdefabcdef" })?.startsWith("Updated to code identity abcdefabcdef"), true);
  assert.equal(codeIdentityUpdate({ revision_reason: "user-save", revision_sha256: "0123" }), null);
  assert.equal(codeIdentityUpdate({ revision_reason: "method-upgrade-confirmed", revision_sha256: "0123" }), null);
  assert.equal(codeIdentityUpdate({}), null);
});
