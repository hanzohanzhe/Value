import { expect, test, type Page } from "@playwright/test";
import { VALUE_101_FALLBACK } from "../app/features/learn/value101";

const sha = "a".repeat(64);
const targetSha = "c".repeat(64);
const slot = { role: "demand.real", label: "Demand", required: true, formats: ["csv"], supported_formats: ["csv"], unit: "MWh", template_available: true, group: "PSM" };
const baseline = { id: "source", name: "BASE study", data_pack_id: "base", revision_number: 1, revision_sha256: sha, start_year: 2025, end_year: 2025, modules: {}, parameters: {}, selected_extensions: [], extension_parameters: {}, maturity_acknowledgements: {}, market_configuration: {}, updated_at: "2026-10-02T00:00:00Z" };
function pack(id: string) { return { id, name: id, data_pack_type: "base", manifest_sha256: id === "base" ? sha : targetSha, country: "SYNTHETIC", timezone: "UTC", bindings: { "demand.real": { filename: "original.csv", sha256: sha, bytes: 12, validation: { status: "valid" } } }, required_count: 1, bound_required_count: 1, valid_required_count: 1, binding_issues: {}, complete: true }; }
async function fixture(page: Page) {
  const projects = [structuredClone(baseline), { ...structuredClone(baseline), id: "other", name: "Referenced study", data_pack_id: "referenced" }];
  const packs = [pack("base"), pack("referenced")];
  const uploads: Array<{ path: string; expected: string | undefined }> = [];
  const derives: unknown[] = [];
  const forbidden: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/**", async (route) => {
    const req = route.request(); const path = new URL(req.url()).pathname; const method = req.method();
    let status = 200; let body: unknown = {};
    if (method === "GET" && path === "/api/workspace") body = { architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [slot], projects, runs: [], data_packs: packs, module_installations: [], extension_installations: [], study_trash: [], runtime: { python: "3.11", compatible: true, selected_capability: "value-native", capabilities: {} } };
    else if (method === "GET" && path === "/api/parameters") body = { parameters: [] };
    else if (method === "GET" && path === "/api/tutorials/value-101") body = VALUE_101_FALLBACK;
    else if (method === "POST" && path === "/api/projects/resolve-draft") body = { schema_version: "value.study-draft-resolution/v1", frontend_contract_version: "value.frontend/v1", valid: true, errors: [], warnings: [], module_slots: [], compatible_modules: {}, system_domains: [], active_dataset_slots: [slot], data_readiness: { required: 1, available: 1, missing_roles: [] }, effective_extension_parameters: {}, maturity: { acknowledgements_required: [] } };
    else if (method === "POST" && path === "/api/data-packs/base/clone") { expect(req.postDataJSON()).toEqual({ schema_version: "value.data-pack-clone-request/v1", name: "My independent BASE", source_manifest_sha256: sha }); const target = pack("copy"); target.name = "My independent BASE"; packs.push(target); status = 201; body = { data_pack: target }; }
    else if (method === "POST" && path === "/api/data-packs/copy/files/demand.real") { uploads.push({ path, expected: req.headers()["x-expected-pack-revision"] }); expect(req.postDataBuffer()?.toString()).toContain("2025"); const target = packs.find((item) => item.id === "copy")!; target.bindings["demand.real"] = { filename: "my-demand.csv", sha256: "d".repeat(64), bytes: 20, validation: { status: "valid" } }; target.manifest_sha256 = "e".repeat(64); body = { data_pack: target }; }
    else if (method === "POST" && path === "/api/projects/source/derive") { const input = req.postDataJSON(); derives.push(input); const project = { ...structuredClone(baseline), id: "derived", name: input.name, data_pack_id: input.data_pack_id }; projects.push(project); status = 201; body = { project, run_started: false }; }
    else if (method === "GET" && /^\/api\/data-workbench\/v1\/(sources|revisions|candidates|bundles)$/.test(path)) { const collection = path.split("/").at(-1)!; body = { schema_version: `value.data-${collection === "bundles" ? "installed-bundles" : collection}/v1`, [collection]: [] }; }
    else { if (method !== "GET") forbidden.push(`${method} ${path}`); status = 404; body = { error: "Unexpected fixture request" }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  return { uploads, derives, packs, assertClean() { expect(forbidden).toEqual([]); expect(errors).toEqual([]); } };
}
async function enter(page: Page) { await page.goto("/"); await expect(page.locator(".service")).toContainText("value-native ready"); await page.getByRole("button", { name: "add your new data", exact: true }).click(); await page.locator(".research-journey:visible").getByRole("combobox", { name: "已有研究", exact: true }).selectOption("source"); }

test("copy BASE, upload only its target role with expected revision, return and derive without Run", async ({ page }) => {
  const f = await fixture(page); await enter(page);
  const journey = page.locator(".research-journey:visible");
  await journey.getByRole("textbox", { name: "新 Study 名称", exact: true }).fill("My changed-data study");
  await journey.getByRole("textbox", { name: "独立数据包名称", exact: true }).fill("My independent BASE");
  await journey.getByRole("button", { name: "复制基线 BASE 包并加入我的文件", exact: true }).click();
  const editor = page.locator(".journey-data-editor:visible");
  await expect(editor).toContainText("My independent BASE");
  await expect(editor.locator('input[type="file"]')).toBeEnabled();
  await editor.getByRole("combobox", { name: "1. 选择文件的语义角色", exact: true }).selectOption("demand.real");
  await editor.locator('input[type="file"]').setInputFiles({ name: "my-demand.csv", mimeType: "text/csv", buffer: Buffer.from("year,mwh\n2025,12\n") });
  await expect(editor).toContainText("SHA 改变 1");
  expect(f.uploads).toEqual([{ path: "/api/data-packs/copy/files/demand.real", expected: targetSha }]);
  expect(f.packs.find((item) => item.id === "base")?.bindings["demand.real"].sha256).toBe(sha);
  await editor.getByRole("button", { name: "保留目标包并返回研究引导", exact: true }).click();
  await expect(journey.getByRole("combobox", { name: "已安装的数据包", exact: true })).toHaveValue("copy");
  await journey.getByRole("button", { name: "创建换数据 Study", exact: true }).click();
  await expect(page).toHaveURL(/[?&]view=run(?:&|$)/);
  expect(f.derives).toEqual([{ intent: "data", name: "My changed-data study", source_revision_sha256: sha, data_pack_id: "copy" }]); f.assertClean();
});

test("referenced target and lost journey context prevent writes at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); const f = await fixture(page); await enter(page);
  const journey = page.locator(".research-journey:visible");
  await journey.getByRole("combobox", { name: "已安装的数据包", exact: true }).selectOption("referenced");
  await journey.getByRole("button", { name: "进入 Data 安装 / 校验", exact: true }).click();
  const editor = page.locator(".journey-data-editor:visible");
  await expect(editor).toContainText("已被保存的 Study 引用"); await expect(editor.locator('input[type="file"]')).toBeDisabled();
  await expect.poll(() => page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  await page.reload();
  await expect(editor).toContainText("引导上下文已失效"); await expect(editor.locator('input[type="file"]')).toBeDisabled();
  expect(f.uploads).toEqual([]); expect(f.derives).toEqual([]); f.assertClean();
});
