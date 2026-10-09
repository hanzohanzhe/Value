import { expect, test } from "@playwright/test";
import { railLink } from "./workspace-nav";

const job = {
  schema_version: "value.data-job/v1",
  job_id: "data-job-browser",
  operation: "discover",
  status: "running",
  progress: 0.25,
};

test("Data Workbench keeps mechanical failures locked and promotes only named reviewed candidates", async ({ page }) => {
  let installed = false;
  await page.route("**/api/data-workbench/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let body: unknown;
    if (path.endsWith("/sources")) body = {
      schema_version: "value.data-sources/v1",
      sources: [{
        schema_version: "value.data-source-definition/v1",
        source_id: "neso.dno-license-areas",
        authority: "NESO",
        semantic_role: "dso_zone_geometry",
        landing_page: "https://www.neso.energy/data-portal/gis-boundaries-gb-dno-license-areas",
        licence_expected: "NESO Open Data Licence",
        candidate_uses: ["DSO resource-zone construction", "audit-map rendering"],
        expected_media_types: ["application/geo+json"],
      }],
    };
    else if (path.endsWith("/revisions")) body = {
      schema_version: "value.data-revisions/v1",
      revisions: [{
        schema_version: "value.data-source-revision/v1",
        source_id: "neso.dno-license-areas",
        revision_id: "2024-05-03",
        publication_date: "2024-05-03",
        landing_page: "https://www.neso.energy/data-portal/gis-boundaries-gb-dno-license-areas",
        download_url: "https://api.neso.energy/dno.geojson",
        media_type: "application/geo+json",
        reported_licence: "NESO Open Data Licence",
        status: "pinned",
        object_key: "sha256/aa/dno.geojson",
      }],
    };
    else if (path.endsWith("/candidates")) body = {
      schema_version: "value.data-candidates/v1",
      candidates: [
        { candidate_id: "candidate-blocked", directory_id: "blocked-review", requested_waivers: [] },
        { candidate_id: "candidate-ready", directory_id: "reviewed-experiment", requested_waivers: ["etys.B6.symmetric_forward_fallback"] },
      ],
    };
    else if (path.endsWith("/bundles")) body = {
      schema_version: "value.data-installed-bundles/v1",
      bundles: installed ? [{
        pack_id: "gb-zonal-reviewed-v1",
        name: "GB zonal reviewed fixture",
        installed_at: "2026-08-21T12:00:00Z",
        validation: { passed: 25, failed: 0, total: 25 },
        installation_boundary: "local_approval_attestation",
      }] : [],
    };
    else if (path.endsWith("/jobs") && request.method() === "POST") body = { job };
    else if (path.endsWith("/jobs/data-job-browser/cancel")) body = {
      job: { ...job, status: "cancel_requested" },
    };
    else if (path.endsWith("/jobs/data-job-browser")) body = { job };
    else if (path.endsWith("/candidate-blocked/validate")) body = {
      schema_version: "value.data-validation-report/v1",
      candidate_id: "candidate-blocked",
      status: "blocked",
      issues: [
        { code: "DW-PACK-001", severity: "blocking", artifact_role: "schema_hash", message: "No promotable pack", evidence: {}, repair: "Assemble a pack", waivable: false },
        { code: "DW-OWNER-001", severity: "blocking", artifact_role: "owner_review", message: "Owner review missing", evidence: {}, repair: "Name a reviewer", waivable: false },
      ],
      gate_results: { source_rights: "passed", schema_hash: "blocked", spatial_topology: "passed", scientific_reconciliation: "passed", determinism_regression: "passed", owner_review: "pending" },
    };
    else if (path.endsWith("/candidate-ready/validate")) body = {
      schema_version: "value.data-validation-report/v1",
      candidate_id: "candidate-ready",
      status: "blocked",
      issues: [
        { code: "DW-SCI-WAIVER-001", severity: "waiver_required", artifact_role: "scientific_reconciliation", message: "Symmetric reverse rating requires acceptance", evidence: { waiver_id: "etys.B6.symmetric_forward_fallback" }, repair: "Accept exact waiver", waivable: true },
        { code: "DW-OWNER-001", severity: "blocking", artifact_role: "owner_review", message: "Owner review missing", evidence: {}, repair: "Name a reviewer", waivable: false },
      ],
      gate_results: { source_rights: "passed", schema_hash: "passed", spatial_topology: "passed", scientific_reconciliation: "waiver_required", determinism_regression: "passed", owner_review: "pending" },
    };
    else if (path.includes("/reports/")) body = {
      schema_version: "value.data-candidate-review/v1",
      candidate_id: path.endsWith("candidate-ready") ? "candidate-ready" : "candidate-blocked",
      status: "blocked",
      candidate_inventory: [{ item_id: "zonal-network", status: "candidate", usable_for: ["experimental zonal runs"], not_usable_for: ["security analysis"], blocking_reasons: [], required_actions: ["owner review"] }],
      blocking_reasons: ["DW-OWNER-001"],
      required_actions: ["Name a reviewer"],
      artifacts: {},
      map_ids: ["zone:north", "zone:south"],
      audit_map_svg: "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 10'><rect width='20' height='10' fill='#2455d6'/></svg>",
    };
    else if (path.endsWith("/candidate-ready/promote")) {
      installed = true;
      body = {
        schema_version: "value.data-signed-bundle-receipt/v1",
        network_pack_id: "gb-zonal-reviewed-v1",
        candidate_id: "candidate-ready",
        bundle_sha256: "a".repeat(64),
        approved_by: "Scientific owner",
        accepted_waivers: ["etys.B6.symmetric_forward_fallback"],
      };
    } else body = { schema_version: "value.data-api-error/v1", error_code: "TEST", error: `Unmocked ${path}` };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.goto("/");
  await railLink(page, "Data").click();
  await expect(page.getByRole("heading", { name: "Data Workbench" })).toBeVisible();

  await page.getByRole("tab", { name: "Official sources" }).click(); // P1 W4b: WAI-ARIA tabs
  await expect(page.getByText("dso zone geometry")).toBeVisible();
  await page.getByRole("button", { name: "Check official catalogues" }).click();
  await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("tab", { name: "Candidates & review" }).click(); // P1 W4b: WAI-ARIA tabs
  await page.getByRole("button", { name: /blocked-review/ }).click();
  await expect(page.getByText("Mechanical gate failure")).toBeVisible();
  await expect(page.getByRole("img", { name: "Candidate audit map supplied by the backend" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve and install bundle" })).toBeDisabled();

  await page.getByRole("button", { name: /reviewed-experiment/ }).click();
  await page.getByLabel("etys.B6.symmetric_forward_fallback").check();
  await page.getByPlaceholder("for example gb-zonal-2026.1").fill("gb-zonal-reviewed-v1");
  await page.getByPlaceholder("Named scientific owner").fill("Scientific owner");
  await page.getByRole("button", { name: "Approve and install bundle" }).click();
  await expect(page.getByText(/installed locally/)).toBeVisible();

  await page.getByRole("tab", { name: "Installed packs" }).click(); // P1 W4b: WAI-ARIA tabs
  await expect(page.getByText("GB zonal reviewed fixture")).toBeVisible();
});
