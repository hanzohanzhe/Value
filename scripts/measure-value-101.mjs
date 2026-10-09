import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";


function argument(name, fallback = undefined) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}


const baseUrl = argument("--base-url", "http://127.0.0.1:8800");
// Run status is read through the UI gateway (P0-1): the API itself needs the
// session token, which only the gateway and the backend hold.
const output = path.resolve(argument(
  "--output",
  "publication/prompt117-value-101-timing.json",
));
const startedAtMs = Number(argument("--started-at-ms", String(Date.now())));
if (!Number.isFinite(startedAtMs) || startedAtMs <= 0) {
  throw new Error("--started-at-ms must be a positive Unix timestamp in milliseconds.");
}

const ledger = [];
let previousMs = startedAtMs;
function mark(id, label, detail = undefined) {
  const observedMs = Date.now();
  ledger.push({
    id,
    label,
    step_seconds: Number(((observedMs - previousMs) / 1000).toFixed(3)),
    cumulative_seconds: Number(((observedMs - startedAtMs) / 1000).toFixed(3)),
    ...(detail ? { detail } : {}),
  });
  previousMs = observedMs;
}

async function completedRun(page, startResponse) {
  const payload = await (await startResponse).json();
  const runId = payload.run.id;
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const response = await page.request.get(`${baseUrl}/api/runs/${runId}`);
    if (response.ok()) {
      const status = await response.json();
      if (status.status === "completed") return runId;
      if (status.status === "failed") {
        throw new Error(`VALUE 101 run ${runId} failed: ${status.error ?? status.current_stage}`);
      }
    }
    await page.waitForTimeout(250);
  }
  throw new Error(`VALUE 101 run ${runId} did not complete within 60 seconds.`);
}

async function openLearn(page) {
  await page.getByRole("button", { name: "Learn: VALUE 101" }).click();
  await page.getByRole("heading", { name: "Build your first VALUE model" }).waitFor();
}

async function runExperiment(page, kind, optionValue) {
  const card = page.locator(".value101-experiment").filter({
    hasText: kind === "data" ? "Data experiment" : "Module experiment",
  });
  await card.locator("select").selectOption(optionValue);
  await card.getByRole("button", { name: "Preview change" }).click();
  await card.getByText("Preview before save", { exact: true }).waitFor();
  await card.getByRole("button", { name: "Create Study" }).click();
  await card.getByRole("button", { name: "Run Study" }).waitFor();
  const start = page.waitForResponse((response) =>
    /\/api\/projects\/[^/]+\/runs$/.test(new URL(response.url()).pathname)
    && response.request().method() === "POST"
  );
  await card.getByRole("button", { name: "Run Study" }).click();
  return completedRun(page, start);
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
let exportedPath;
try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  mark("local_site_ready", "The local VALUE site loaded");

  await openLearn(page);
  await page.getByRole("button", { name: "Open lesson" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  mark("lesson_completed", "The five VALUE building blocks were read");

  await page.getByRole("button", { name: "Create baseline Study" }).first().click();
  await page.getByRole("button", { name: "Baseline Study created" }).waitFor();
  mark("baseline_study_created", "Create baseline Study", { run_started: false });

  const baselineStart = page.waitForResponse((response) =>
    /\/api\/projects\/[^/]+\/runs$/.test(new URL(response.url()).pathname)
    && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Run baseline" }).click();
  const baselineRunId = await completedRun(page, baselineStart);
  mark("baseline_completed", "Run baseline", { run_id: baselineRunId });

  await openLearn(page);
  const dataRunId = await runExperiment(page, "data", "value-101-windy-v1");
  mark("data_variant_completed", "Preview change, Create Study and run the Windy data experiment", { run_id: dataRunId });

  await openLearn(page);
  const storageRunId = await runExperiment(page, "storage", "value-legacy-storage-tariff");
  mark("storage_variant_completed", "Preview change, Create Study and run the legacy storage-pricing experiment", { run_id: storageRunId });

  await openLearn(page);
  await page.getByRole("heading", { name: "Compare three controlled Runs" }).waitFor();
  await page.getByText("Controlled three-way comparison", { exact: true }).waitFor();
  mark("comparison_ready", "Compare three controlled Runs", {
    run_ids: [baselineRunId, dataRunId, storageRunId],
  });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export completion JSON" }).click();
  const download = await downloadPromise;
  exportedPath = path.join(os.tmpdir(), `value-101-completion-${crypto.randomUUID()}.json`);
  await download.saveAs(exportedPath);
  const bytes = fs.readFileSync(exportedPath);
  mark("completion_exported", "Export completion JSON", {
    filename: download.suggestedFilename(),
    bytes: bytes.length,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
  });

  const finishedAtMs = Date.now();
  const report = {
    schema_version: "value.101-timing/v1",
    measurement: "automated stopwatch over the ordinary local learner UI",
    start_boundary: "local VALUE page navigation",
    finish_boundary: "completion JSON download saved",
    base_url: baseUrl,
    started_at: new Date(startedAtMs).toISOString(),
    finished_at: new Date(finishedAtMs).toISOString(),
    total_seconds: Number(((finishedAtMs - startedAtMs) / 1000).toFixed(3)),
    target_seconds: 1800,
    within_target: finishedAtMs - startedAtMs <= 1_800_000,
    learner_think_time_included: false,
    scientific_boundary: "Three 48-period teaching runs; not annual British evidence.",
    steps: ledger,
  };
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
} finally {
  if (exportedPath) fs.rmSync(exportedPath, { force: true });
  await browser.close();
}
