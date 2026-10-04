import { expect, test } from "@playwright/test";
import { VALUE_101_FALLBACK } from "../app/features/learn/value101";

const ACK = "value.experimental-ack/v1";
const candidateAck = (id: string) => `module:${id}@1.0.0`;
function latch() {
  let resolve!: () => void;
  const promise = new Promise<void>(done => { resolve = done; });
  return { promise, resolve };
}
const modules = ["original", "candidate-a", "candidate-b"].map(id => ({
  id, name: id, slot: "storage_cost", version: "1.0.0", kind: "cem", status: id === "original" ? "ready" : "experimental",
  inputs: [], outputs: [], description: "Author fixture", contract_version: "value.contracts/v2",
}));
const sourceA = { id: "source-a", name: "Source A", revision_sha256: "a".repeat(64), revision_number: 1,
  data_pack_id: "pack-a", start_year: 2025, end_year: 2026, updated_at: "2026-10-02T00:00:00Z",
  modules: { storage_cost: "original", psm: "preserved-psm" }, parameters: { fixed: 31 },
  runtime_options: { trace: "summary" }, selected_extensions: [], extension_parameters: {}, market_configuration: {},
  maturity_acknowledgements: { [candidateAck("candidate-a")]: ACK, [candidateAck("candidate-b")]: ACK, "module:preserved-psm@1.0.0": ACK },
};
const sourceB = { ...structuredClone(sourceA), id: "source-b", name: "Source B", data_pack_id: "pack-b", revision_sha256: "b".repeat(64) };

function detail(id: string) {
  const module = modules.find(item => item.id === id)!;
  return { schema_version: "value.module-authoring/v1", module_id: id, identity_sha256: `identity-${id}`,
    identity: { module_id: id, module_version: module.version, slot: module.slot, contract_version: module.contract_version,
      entry_point: `fixture_${id.replaceAll("-", "_")}:Plugin`, source_sha256: `source-hash-${id}`, scientific_version: null, execution_kind: "live_module" },
    manifest: { id, version: module.version, slot: module.slot, contract_version: module.contract_version, status: module.status,
      inputs: [], outputs: [], state_reads: [], state_writes: [], parameters: [], provides_capabilities: [], requires_capabilities: [], artifacts: [], units: {}, determinism: "deterministic" },
    methods: ["create"], source: { available: true, filename: "plugin.py", content: `# Source for ${id}`, truncated: false, reason: null },
    conformance: { status: "not_run", errors: [], warnings: [], scientific_validation_status: "not_evaluated", origin: null },
  };
}
type Draft = { data_pack_id: string; modules: Record<string, string>; maturity_acknowledgements: Record<string, string> };
function resolution(body: Draft) {
  const id = body.modules.storage_cost ?? "original";
  const required = id.startsWith("candidate-");
  const valid = !required || body.maturity_acknowledgements[candidateAck(id)] === ACK;
  return { schema_version: "value.study-draft-resolution/v1", valid,
    errors: valid ? [] : [{ code: "GF_EXPERIMENTAL_ACK_REQUIRED", message: "Confirm the current candidate version", scope: "maturity" }],
    warnings: [{ code: "FIXTURE_CONTEXT", message: `Current evidence ${body.data_pack_id}/${id}`, scope: "study" }],
    compatible_modules: { storage_cost: [{ id, compatible: true, reason: null }] },
    module_slots: [], system_domains: [], active_dataset_slots: [], effective_extension_parameters: {},
    data_readiness: { required: 0, available: 0, missing_roles: [] },
    maturity: { acknowledgement_contract: ACK, acknowledgements_required: required ? [{ key: candidateAck(id), id, version: "1.0.0", maturity: "experimental", acknowledgement: ACK }] : [] },
    graph_preview: { modules: { storage_cost: { module_id: id, module_version: "1.0.0", contract_version: "value.contracts/v2" } } },
  };
}

test("module author discards late contexts and requires fresh candidate consent before a narrow Study save", async ({ page }) => {
  const sourceBefore = structuredClone([sourceA, sourceB]);
  const projects = structuredClone([sourceA, sourceB]);
  const drafts: Draft[] = [], derived: Array<{ path: string; body: Record<string, unknown> }> = [];
  const forbiddenWrites: string[] = [], errors: string[] = [];
  const oldStarted = latch(), oldRelease = latch(), oldDone = latch();
  const nextStarted = latch(), nextRelease = latch(), nextDone = latch();
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    let body: unknown = {}, status = 200, delayedDone: ReturnType<typeof latch> | undefined;
    if (request.method() === "POST" && path === "/api/projects/resolve-draft") {
      const input = request.postDataJSON() as Draft;
      if (input.modules.storage_cost?.startsWith("candidate-")) drafts.push(structuredClone(input));
      if (input.modules.storage_cost === "candidate-a" && input.data_pack_id === "pack-a" && input.maturity_acknowledgements[candidateAck("candidate-a")] === ACK) {
        oldStarted.resolve(); await oldRelease.promise; delayedDone = oldDone;
      }
      if (input.modules.storage_cost === "candidate-b" && input.data_pack_id === "pack-b" && input.maturity_acknowledgements[candidateAck("candidate-b")] === ACK) {
        nextStarted.resolve(); await nextRelease.promise; delayedDone = nextDone;
      }
      body = resolution(input);
    } else if (request.method() === "POST" && path === "/api/projects/source-b/derive") {
      const input = request.postDataJSON() as Record<string, unknown>;
      derived.push({ path, body: input });
      const saved = { ...structuredClone(sourceB), id: "derived-method-study", name: String(input.name),
        revision_sha256: "d".repeat(64), modules: { ...sourceB.modules, storage_cost: "candidate-b" } };
      projects.push(saved); body = { ok: true, project: saved, run_started: false };
    } else if (request.method() !== "GET") {
      forbiddenWrites.push(path); status = 405; body = { error: "Fixture blocks Run and other writes" };
    } else if (path === "/api/workspace") body = { architecture_version: "value.contracts/v2", modules,
      module_slots: [], extensions: [], dataset_slots: [], projects, runs: [], module_installations: [], extension_installations: [], study_trash: [],
      data_packs: ["pack-a", "pack-b"].map(id => ({ id, name: id, country: "SYNTHETIC", timezone: "UTC", bindings: {}, complete: true,
        required_count: 0, bound_required_count: 0, valid_required_count: 0, binding_issues: {} })), runtime: { python: "3.11", compatible: true, capabilities: {} } };
    else if (/^\/api\/modules\/[^/]+\/authoring$/.test(path)) body = detail(decodeURIComponent(path.split("/")[3]));
    else if (path === "/api/parameters") body = { parameters: [] };
    else if (path === "/api/tutorials/value-101") body = VALUE_101_FALLBACK;
    else { status = 404; body = { error: "No scientific evidence recorded in this author fixture" }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }).catch(() => {});
    delayedDone?.resolve();
  });

  await page.goto("/?view=models&path=module");
  const panel = page.locator(".module-author-workbench:visible");
  const save = panel.getByRole("button", { name: "Create Study with this module", exact: true });
  await expect(panel).toHaveCount(1);
  await panel.getByRole("combobox", { name: "Author candidate module" }).selectOption("candidate-a");
  await panel.getByRole("combobox", { name: "Module source Study" }).selectOption("source-a");
  const ackA = panel.getByRole("checkbox", { name: /I acknowledge candidate-a 1.0.0/ });
  await expect(ackA).not.toBeChecked(); await expect(save).toBeDisabled();
  expect(drafts.at(-1)?.maturity_acknowledgements[candidateAck("candidate-a")]).toBeUndefined();
  await ackA.check(); await oldStarted.promise;
  await expect(save).toBeDisabled();

  await panel.getByRole("combobox", { name: "Module source Study" }).selectOption("source-b");
  await expect(ackA).not.toBeChecked(); await expect(save).toBeDisabled();
  await panel.getByRole("combobox", { name: "Author candidate module" }).selectOption("candidate-b");
  const ackB = panel.getByRole("checkbox", { name: /I acknowledge candidate-b 1.0.0/ });
  await expect(ackB).not.toBeChecked(); await expect(save).toBeDisabled();
  await expect(panel).toContainText("Current evidence pack-b/candidate-b");
  oldRelease.resolve(); await oldDone.promise;
  await expect(panel).not.toContainText("Current evidence pack-a/candidate-a");
  await expect(ackB).not.toBeChecked(); await expect(save).toBeDisabled();
  expect(drafts.at(-1)?.maturity_acknowledgements[candidateAck("candidate-b")]).toBeUndefined();

  await ackB.check(); await nextStarted.promise;
  await expect(save).toBeDisabled();
  nextRelease.resolve(); await nextDone.promise;
  await expect(save).toBeEnabled();
  await save.click();
  await expect.poll(() => derived.length).toBe(1);
  await expect(page).toHaveURL(/[?&]view=run(?:&|$)/);
  expect(derived).toEqual([{ path: "/api/projects/source-b/derive", body: {
    intent: "edit_module", name: "My module experiment", data_pack_id: "pack-b", source_revision_sha256: sourceB.revision_sha256,
    slot: "storage_cost", module_id: "candidate-b", candidate_identity_sha256: "identity-candidate-b",
    maturity_acknowledgements: { [candidateAck("candidate-b")]: ACK },
  } }]);
  expect(projects.slice(0, 2)).toEqual(sourceBefore);
  expect(forbiddenWrites).toEqual([]); expect(errors).toEqual([]);
});
