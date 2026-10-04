// Offline e2e ratchet (P0-9 S0): compares a Playwright JSON report with
// e2e/offline-subset.json. The rules mirror the backend test ratchet:
//   * a failing test that is not registered is a NEW failure (gate fails);
//   * a registered failure that now passes must be removed from the registry
//     (otherwise a fixed spec could silently regress again);
//   * every registered spec must actually have run (a missing report or a
//     renamed test must not read as green), and a registered failure that is
//     now skipped (test.skip / test.fixme / a skip condition) did not run either;
//   * skipped tests are reported, never counted as passes;
//   * a registered failure may pin *why* it fails: with "error_must_match"
//     (a regular expression) every error of that test must match it, so a
//     test registered for one known assertion cannot hide a second breakage.
// Test identity is "<spec file> > <title path>", not a line number, because
// line numbers move with every edit.

// ANSI colour codes that Playwright puts into error messages.
const ANSI = /\u001b\[[0-9;]*m/g;

function errorMessages(result) {
  const errors = result?.errors?.length ? result.errors : result?.error ? [result.error] : [];
  return errors.map((error) => String(error?.message ?? error?.value ?? "").replace(ANSI, ""));
}

export function flattenReport(report) {
  const rows = [];
  const walk = (suite, titles) => {
    const here = suite.title && !/\.spec\.[cm]?[jt]s$/.test(suite.title) ? [...titles, suite.title] : titles;
    for (const spec of suite.specs ?? []) {
      for (const test of spec.tests ?? []) {
        const results = test.results ?? [];
        const last = results.at(-1);
        const final = last?.status ?? (test.status === "skipped" ? "skipped" : "unknown");
        rows.push({
          id: `${spec.file ?? suite.file} > ${[...here, spec.title].join(" > ")}`,
          file: spec.file ?? suite.file,
          project: test.projectName ?? "",
          status: test.status === "skipped" ? "skipped" : final === "passed" ? "passed" : final,
          errors: errorMessages(last),
        });
      }
    }
    for (const child of suite.suites ?? []) walk(child, here);
  };
  for (const suite of report.suites ?? []) walk(suite, []);
  return rows;
}

export function evaluateOffline(report, subset) {
  const rows = flattenReport(report);
  const known = new Map((subset.known_failures ?? []).map((entry) => [entry.id, entry]));
  const specs = new Set(subset.specs.map((name) => name.replace(/^e2e\//, "")));
  const inScope = rows.filter((row) => specs.has(row.file));
  const failed = inScope.filter((row) => !["passed", "skipped"].includes(row.status));
  const passed = inScope.filter((row) => row.status === "passed");
  const skipped = inScope.filter((row) => row.status === "skipped");
  const newFailures = failed.filter((row) => !known.has(row.id)).map((row) => row.id);
  const passedIds = new Set(passed.map((row) => row.id));
  const fixedButListed = [...known.keys()].filter((id) => passedIds.has(id));
  const knownMissing = [...known.keys()].filter((id) => !inScope.some((row) => row.id === id));
  const skippedKnown = [...known.keys()].filter((id) => skipped.some((row) => row.id === id));
  const unexpectedErrors = [];
  for (const row of failed) {
    const pattern = known.get(row.id)?.error_must_match;
    if (!pattern) continue;
    const expected = new RegExp(pattern);
    const stray = row.errors.length ? row.errors.filter((message) => !expected.test(message)) : ["(no error message recorded)"];
    for (const message of stray) unexpectedErrors.push(`${row.id}: ${message.split("\n")[0]}`);
  }
  const specsNotRun = [...specs].filter((name) => !inScope.some((row) => row.file === name));
  const perSpec = {};
  for (const name of specs) {
    const own = inScope.filter((row) => row.file === name);
    perSpec[name] = {
      passed: own.filter((row) => row.status === "passed").length,
      failed: own.filter((row) => !["passed", "skipped"].includes(row.status)).length,
      skipped: own.filter((row) => row.status === "skipped").length,
    };
  }
  const minimums = Object.entries(subset.min_passed ?? {})
    .map(([name, minimum]) => [name.replace(/^e2e\//, ""), minimum])
    .filter(([name, minimum]) => (perSpec[name]?.passed ?? 0) < minimum)
    .map(([name, minimum]) => `${name}: ${perSpec[name]?.passed ?? 0} passed < required ${minimum}`);
  const ok = !newFailures.length && !fixedButListed.length && !knownMissing.length && !skippedKnown.length && !specsNotRun.length && !minimums.length && !unexpectedErrors.length;
  return {
    ok, perSpec, newFailures, fixedButListed, knownMissing, skippedKnown, specsNotRun, minimums, unexpectedErrors,
    totals: { passed: passed.length, failed: failed.length, skipped: skipped.length, known_failures: failed.length - newFailures.length },
  };
}

export function describeEvaluation(result) {
  const lines = [`offline e2e: ${result.totals.passed} passed, ${result.totals.known_failures} known failure(s), ${result.totals.skipped} skipped, ${result.newFailures.length} new failure(s)`];
  for (const [name, row] of Object.entries(result.perSpec)) lines.push(`  ${name}: ${row.passed} passed, ${row.failed} failed, ${row.skipped} skipped`);
  for (const id of result.newFailures) lines.push(`NEW FAILURE ${id}`);
  for (const id of result.fixedButListed) lines.push(`FIXED BUT STILL REGISTERED (remove from e2e/offline-subset.json) ${id}`);
  for (const id of result.knownMissing) lines.push(`REGISTERED TEST DID NOT RUN ${id}`);
  for (const id of result.skippedKnown ?? []) lines.push(`REGISTERED TEST WAS SKIPPED ${id}`);
  for (const name of result.specsNotRun) lines.push(`SPEC PRODUCED NO RESULTS ${name}`);
  for (const line of result.minimums) lines.push(`BELOW MINIMUM ${line}`);
  for (const line of result.unexpectedErrors) lines.push(`REGISTERED FAILURE BROKE DIFFERENTLY ${line}`);
  return lines.join("\n");
}
